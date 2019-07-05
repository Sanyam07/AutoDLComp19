import torch.utils.data as data

from nvidia.dali.pipeline import Pipeline
import nvidia.dali.ops as ops
import nvidia.dali.types as types

from PIL import Image
import os
import os.path
import numpy as np
import torch
from numpy.random import randint


class VideoRecord(object):
    def __init__(self, row):
        self._data = row

    @property
    def path(self):
        return self._data[0]

    @property
    def num_frames(self):
        return int(self._data[1])

    @property
    def labels(self):
        return self._data[2:]


class TSNDataSet(data.Dataset):
    def __init__(self, root_path, list_file,
                 num_segments=3, new_length=1, modality='RGB',
                 image_tmpl='img_{:05d}.jpg', transform=None,
                 force_grayscale=False, random_shift=True, test_mode=False,
                 classification_type='multiclass', num_labels=None):

        self.root_path = root_path
        self.list_file = list_file
        self.num_segments = num_segments
        self.new_length = new_length
        self.modality = modality
        self.image_tmpl = image_tmpl
        self.transform = transform
        self.random_shift = random_shift
        self.test_mode = test_mode
        self.classification_type = classification_type
        self.num_labels = num_labels


        if self.modality == 'RGBDiff':
            self.new_length += 1  # Diff needs one more image to calculate diff

        self._parse_list()

    def _load_image(self, directory, idx):
        if self.modality == 'RGB' or self.modality == 'RGBDiff':
            return [Image.open(os.path.join(directory, self.image_tmpl.format(idx))).convert('RGB')]
        elif self.modality == 'Flow':
            x_img = Image.open(os.path.join(directory, self.image_tmpl.format('x', idx))).convert('L')
            y_img = Image.open(os.path.join(directory, self.image_tmpl.format('y', idx))).convert('L')

            return [x_img, y_img]

    def _parse_list(self):
        # self.video_list = [VideoRecord(x.strip().split(' ')) for x in open(self.list_file)]  # noqa: E501
        self.video_list = []
        for x in open(self.list_file):
            data = x.strip().split(' ')
            path = '{}{}'.format(self.root_path, data[0]).replace('//', '/')
            self.video_list.append(VideoRecord([path] + data[1:]))

    def _sample_indices(self, record):
        """

        :param record: VideoRecord
        :return: list
        """

        average_duration = (record.num_frames - self.new_length + 1) // self.num_segments
        if average_duration > 0:
            offsets = np.multiply(list(range(self.num_segments)), average_duration) + randint(average_duration,
                                                                                              size=self.num_segments)
        elif record.num_frames > self.num_segments:
            offsets = np.sort(randint(record.num_frames - self.new_length + 1, size=self.num_segments))
        else:
            offsets = np.zeros((self.num_segments,))
        return offsets + 1

    def _get_val_indices(self, record):
        if record.num_frames > self.num_segments + self.new_length - 1:
            tick = (record.num_frames - self.new_length + 1) / float(self.num_segments)
            offsets = np.array([int(tick / 2.0 + tick * x) for x in range(self.num_segments)])
        else:
            offsets = np.zeros((self.num_segments,))
        return offsets + 1

    def _get_test_indices(self, record):

        tick = (record.num_frames - self.new_length + 1) / float(self.num_segments)

        offsets = np.array([int(tick / 2.0 + tick * x) for x in range(self.num_segments)])

        return offsets + 1

    def __getitem__(self, index):
        record = self.video_list[index]

        if not self.test_mode:
            segment_indices = self._sample_indices(record) if self.random_shift else self._get_val_indices(record)
        else:
            segment_indices = self._get_test_indices(record)

        return self.get(record, segment_indices)

    def get(self, record, indices):

        images = list()
        for seg_ind in indices:
            p = int(seg_ind)
            for i in range(self.new_length):
                seg_imgs = self._load_image(record.path, p)
                images.extend(seg_imgs)
                if p < record.num_frames:
                    p += 1

        process_data = self.transform(images)

        if self.classification_type == 'multiclass':
            label = int(record.labels[0])
        elif self.classification_type == 'multilabel':
            label = torch.zeros([self.num_labels])
            for idx, perc in zip(record.labels[::2], record.labels[1::2]):
                label[int(idx)] = float(perc)
        else:
            raise NotImplementedError('unknown classification type: ' + str(self.classification_type))

        return process_data, label

    def __len__(self):
        return len(self.video_list)


class VideoDataSet():
    def __init__(self, root_path, list_file, num_segments=3, batch_size=1,
                 num_threads=1, device_id=0, shuffle=True,
                 classification_type='multiclass', num_labels=None):
        self.root_path = root_path
        self.list_file = list_file
        self.num_segments = num_segments
        self.classification_type = classification_type
        self.num_labels = num_labels
        self.batch_size = batch_size

        self._parse_list()
        data = [elem.path for elem in self.video_list]
        self.pipe = VideoPipe(batch_size=batch_size, sequence_length=num_segments,
                              num_threads=num_threads, device_id=0, data=data, shuffle=shuffle)
        self.pipe.build()


    def _parse_list(self):
        self.video_list = []
        for x in open(self.list_file):
            data = x.strip().split(' ')
            path = '{}{}'.format(self.root_path, data[0]).replace('//', '/')
            self.video_list.append(VideoRecord([path] + data[1:]))

    def __iter__(self):
        return self

    def __next__(self):
        return (self.pipe.run()


class VideoPipe(Pipeline):
    def __init__(self, batch_size, sequence_length, num_threads, device_id, data, shuffle):
        super(VideoPipe, self).__init__(batch_size, num_threads, device_id, seed=16)
        self.input = ops.VideoReader(device="gpu", filenames=data, sequence_length=sequence_length,
                                     shard_id=0, num_shards=1,
                                     random_shuffle=shuffle, initial_fill=16)

    def define_graph(self):
        output = self.input(name="Reader")
        return output


