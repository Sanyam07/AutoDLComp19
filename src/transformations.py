import time
from collections import OrderedDict
import numpy as np
import torch
import torch.nn as nn
from torchvision import transforms

from utils import LOGGER, MonkeyNet

RESIZE_FACTOR = 1.3


# ########################################################
# Perform only necessary transformations on the cpu
# ########################################################
def baseline_transforms(autodl_model, dataset):
    LOGGER.info('Using ###   BaselineAugmentNet   ### for transformations')

    # Monkeypatch the new network to expose the original model's attributes
    # and stack them
    autodl_model.model = MonkeyNet(OrderedDict([
        ('baseline_aug_net', BaselineAugmentNet()),
        ('main_net', autodl_model.model),
    ]))
    transf_dict = {
        'train': {
            'samples': transforms.Compose(
                [
                    CPUSelectSegmentsDynamic(autodl_model.model),
                    RandomCropPad(autodl_model.model.input_size)
                ]
            ),
            'labels': transforms.Lambda(
                lambda x: x if dataset.is_multilabel else np.argmax(x)
            )
        },
        'test': {
            'samples': transforms.Compose(
                [
                    CPUSelectSegmentsDynamic(autodl_model.model),
                    RandomCropPad(autodl_model.model.input_size)
                ]
            ),
            'labels': transforms.Lambda(
                lambda x: x if dataset.is_multilabel else np.argmax(x)
            )
        }
    }
    return transf_dict


class BaselineAugmentNet(nn.Module):
    def __init__(self):
        super().__init__()
        self.augmentation = {
            'train': (
                nn.Sequential(
                    SwapAxes(),
                    FormatChannels(3),
                    Stack(),
                    Normalize()
                )
            ),
            'eval': (
                nn.Sequential(
                    SwapAxes(),
                    FormatChannels(3),
                    Stack(),
                    Normalize()
                )
            )
        }

    def forward(self, x):
        mode = 'train' if self.training else 'eval'
        x = self.augmentation[mode](x)
        return x


def aug_net(autodl_model, dataset, use_gpu_resize):
    model = autodl_model.model
    LOGGER.info('Using ###   aug_net   ### for transformations')

    # Inject the WrapperNet at the top of the modules list
    cpu_resize = (
        np.any(dataset.min_shape[1:] != dataset.max_shape[1:])
        or not use_gpu_resize
    )
    aug_net = AugmentNet(model.input_size, not cpu_resize)
    # Monkeypatch the new network to expose the original model's attributes
    autodl_model.model = MonkeyNet(OrderedDict([
        ('aug_net', aug_net),
        ('main_net', model)
    ]))
    transf_dict = {
        'train': {
            'samples': transforms.Compose(
                [
                    CPUSelectSegmentsDynamic(autodl_model.model),
                    *(
                        (CPUResizeImage(aug_net.re_size.tolist()), )
                        if cpu_resize else ()
                    )
                ]
            ),
            'labels': transforms.Lambda(
                lambda x: x if dataset.is_multilabel else np.argmax(x)
            )
        },
        'test': {
            'samples': transforms.Compose(
                [
                    CPUSelectSegmentsDynamic(autodl_model.model),
                    *(
                        (CPUResizeImage(aug_net.out_size.tolist()), )
                        if cpu_resize else ()
                    )
                ]
            ),
            'labels': transforms.Lambda(
                lambda x: x if dataset.is_multilabel else np.argmax(x)
            )
        }
    }
    return transf_dict


class AugmentNet(nn.Module):
    def __init__(self, out_size: int, fast_augment: bool):
        super().__init__()
        if not isinstance(out_size, int):
            raise ValueError
        self.fast_augment = fast_augment
        self.out_size = np.array((out_size, out_size), dtype=np.int)
        self.re_size = np.ceil(self.out_size * RESIZE_FACTOR).astype(np.int)
        self.augmentation = {
            'train': (
                nn.Sequential(
                    SwapAxes(),
                    FormatChannels(3),
                    Interpolate(self.re_size.tolist()),
                    RandomCrop(self.out_size.tolist()),
                    Stack(),
                    Normalize()
                ) if self.fast_augment
                else nn.Sequential(
                    SwapAxes(),
                    FormatChannels(3),
                    RandomCrop(self.out_size.tolist()),
                    Stack(),
                    Normalize()
                )
            ),
            'eval': (
                nn.Sequential(
                    SwapAxes(),
                    FormatChannels(3),
                    Interpolate(self.out_size.tolist()),
                    Stack(),
                    Normalize()
                ) if self.fast_augment
                else nn.Sequential(
                    SwapAxes(),
                    FormatChannels(3),
                    RandomCrop(self.out_size.tolist()),
                    Stack(),
                    Normalize()
                )
            )
        }

    def forward(self, x):
        mode = 'train' if self.training else 'eval'
        x = self.augmentation[mode](x)
        return x


# ########################################################
# Helpers
# ########################################################
class FormatChannels(nn.Module):
    '''
    Adapt number of channels. If there are more than desired, use only the first n channels.
    If there are less, copy existing channels
    '''
    def __init__(self, channels_des):
        super().__init__()
        self.channels_des = channels_des

    def forward(self, x):
        channels = x.shape[2]
        if channels < self.channels_des:
            shape = x.shape
            x = x.expand(*shape[:2], int(np.ceil(self.channels_des / channels)), *shape[3:])
        x = x[:, :, 0:self.channels_des, :, :].contiguous()

        return x


class SwapAxes(nn.Module):
    '''
    Swap axes for interpolation
    '''
    def __init__(self):
        super().__init__()
        pass

    def forward(self, x):
        x = x.permute(0, 1, 4, 2, 3)
        return x


class Interpolate(nn.Module):
    '''
    Resize image to desired size
    '''
    def __init__(self, size):
        super().__init__()
        self.size = size
        self.interp = nn.functional.interpolate

    def forward(self, x):
        # first squeeze first two dimensions to make it suitable for interpolation
        shape = x.shape
        x = x.view(-1, *shape[2:])
        # do interpolation
        x = self.interp(x, size=self.size, mode='nearest')
        # and unsqueeeze dimensions again
        x = x.view(*shape[0:3], *self.size)
        return x


class RandomCrop(nn.Module):
    '''
    Randomly crop a selection of the image
    '''
    def __init__(self, size):
        super().__init__()
        self.size = size

    def forward(self, x):
        # input shape
        row_in = x.shape[-2]
        col_in = x.shape[-1]
        # output shape
        row_out = self.size[0]
        col_out = self.size[1]
        # random start index for crop
        row_start = int(np.random.random() * (row_in - row_out))
        col_start = int(np.random.random() * (col_in - col_out))
        # resulting end index for crop
        row_end = int(row_start + row_out)
        col_end = int(col_start + col_out)
        # row_index = torch.tensor([row_start, row_end])
        # col_index = torch.tensor([col_start, col_end])
        x = x[:, :, :, row_start:row_end, col_start:col_end]
        return x


class RandomCropPad(object):
    def __init__(self, size_des):
        self.size_des = size_des

    def __call__(self, pics):
        row = pics.shape[1]
        row_des = self.size_des
        col = pics.shape[2]
        col_des = self.size_des

        row_rand = -1
        col_rand = -1

        if row <= row_des: # pad rows
            row_pad_start = int(np.floor((row_des-row)/2))
            row_pad_end = row + int(np.floor((row_des-row)/2))
            row_start = 0
            row_end = row
        else: # crop rows
            row_rand = int(np.random.random() * int(np.floor((row-row_des))))
            row_pad_start = 0
            row_pad_end = row_des
            row_start = row_rand
            row_end = row_des + row_rand
        if col <= col_des: # pad columns
            col_pad_start = int(np.floor((col_des-col)/2))
            col_pad_end = col + int(np.floor((col_des-col)/2))
            col_start = 0
            col_end = col
        else: # crop columns
            col_rand = int(np.random.random() * int(np.floor((col-col_des))))
            col_pad_start = 0
            col_pad_end = col_des
            col_start = col_rand
            col_end = col_des + col_rand

        pics_pad = np.zeros((pics.shape[0], row_des, col_des, pics.shape[3]), dtype=pics.dtype)
        pics_pad[:,row_pad_start:row_pad_end,col_pad_start:col_pad_end,:] = pics[:,row_start:row_end,col_start:col_end,:]
        return pics_pad


class Stack(nn.Module):
    '''
    Concatenate subsequent images of one video by stacking the channels
    '''
    def __init__(self):
        super().__init__()

    def forward(self, x):
        shape = x.shape
        shape_new = [x.shape[0], x.shape[1] * x.shape[2], *shape[3:]]
        x = x.view(*shape_new)
        return x


class Normalize(nn.Module):
    '''
    Normalize from the 0-255 range to the 0-1 range.
    '''
    def __init__(self):
        super().__init__()

    def forward(self, x):
        min_val = torch.min(x).cpu().numpy()

        if min_val < -0.01:
            x = x + min_val

        max_val = torch.max(x).cpu().numpy()

        if max_val <= 255 and max_val > 1:
            x = x / 255
        elif max_val > 255:
            x = x / max_val
            LOGGER.warning('Weird max_val: ' + str(max_val))

        return x


class CPUFormatLabel(nn.Module):
    def __init__(self, multilabel):
        super().__init__()
        self.is_multilabel = multilabel

    def __call__(self, x: torch.Tensor):
        x = x if self.is_multilabel else np.argmax(x, axis=0)
        return x

    def forward(self, x):
        return self(x)


class CPUSelectSegmentsDynamic(nn.Module):
    def __init__(self, model, random=True):
        super().__init__()
        self.master_model = model

    def __call__(self, x: torch.Tensor):
        choices = []
        num_segments = self.master_model.num_segments
        if x.shape[0] <= num_segments:
            choices = np.linspace(0, x.shape[0] - 1, num_segments, dtype=int)
        else:
            choices = np.linspace(0, x.shape[0] - 1, x.shape[0], dtype=int)
            choices = np.array_split(choices, num_segments)
            choices = [np.random.choice(c, 1)[0].tolist() for c in choices]
        x = x[choices]
        return x


class CPUSelectSegments(nn.Module):
    def __init__(self, num_segments, random=True):
        super().__init__()
        self.num_segments = num_segments

    def __call__(self, x: torch.Tensor):
        choices = []
        if x.shape[0] <= self.num_segments:
            choices = np.linspace(0, x.shape[0] - 1, self.num_segments, dtype=int)
        else:
            choices = np.linspace(0, x.shape[0] - 1, x.shape[0], dtype=int)
            choices = np.array_split(choices, self.num_segments)
            choices = np.array([np.random.choice(c, 1) for c in choices]).squeeze()
        x = x[choices.tolist()]
        return x


class CPUFormatImage(nn.Module):
    def __init__(self, to_pil_image):
        super().__init__()
        self.to_pil_image = to_pil_image
        self.convert_to_pil = transforms.ToPILImage()

    def __call__(self, x):
        if self.to_pil_image:
            x = [self.convert_to_pil(e) for e in x[:]]
        else:
            x = np.moveaxis(x, 3, 1)
        return x


class CPUNormImage(nn.Module):
    def __call__(self, x):
        x = x / 255 if x.max() > 1. else x
        if x.shape[1] < 3:
            x = np.repeat(x, 3, 1)
        return x


class CPUResizeImage(nn.Module):
    def __init__(self, target_im_size):
        super().__init__()
        self.target_im_size = (
            (target_im_size, target_im_size)
            if isinstance(target_im_size, int)
            else target_im_size
        )
        self.convert_to_pil = transforms.ToPILImage()

    def __call__(self, x):
        x = [self.convert_to_pil(e) for e in x[:]]
        x = [e.resize(self.target_im_size) for e in x]
        x = np.array([np.array(e) for e in x])
        if len(x.shape) < 4:
            x = np.expand_dims(x, -1)
        return x


class CPURandomCropPad(nn.Module):
    def __init__(self, target_im_size):
        super().__init__()
        self.target_im_size = (
            (target_im_size, target_im_size)
            if isinstance(target_im_size, int)
            else target_im_size
        )

    def __call__(self, x):
        # expects FxWxHxC Format
        im_size = np.array(x.shape[1:-1])
        wiggle_room = im_size - self.target_im_size

        wi = int(np.random.choice(np.arange(
            wiggle_room[0],
            0,
            -np.sign(wiggle_room[0]),
            dtype=np.int
        ), 1))
        hi = int(np.random.choice(np.arange(
            wiggle_room[1],
            0,
            -np.sign(wiggle_room[1]),
            dtype=np.int
        ), 1))

        wis, wie = (wi, wi + self.target_im_size[0])
        nwis, nwie = (0, self.target_im_size[0])
        if wi < 0:
            wis, wie = (0, im_size[0])
            nwis, nwie = (-im_size[0] + wi, wi)

        his, hie = (hi, hi + self.target_im_size[1])
        nhis, nhie = (0, self.target_im_size[1])
        if hi < 0:
            his, hie = (0, im_size[1])
            nhis, nhie = (-im_size[1] + hi, hi)

        new_x = np.zeros((x.shape[0], *self.target_im_size, x.shape[-1]), dtype=x.dtype)
        new_x[:, nwis:nwie, nhis:nhie, :] = x[:, wis:wie, his:hie, :]
        return new_x


class CPUStackSegments(nn.Module):
    def __call__(self, x):
        x = x.reshape((-1, *x.shape[2:]))
        return x
