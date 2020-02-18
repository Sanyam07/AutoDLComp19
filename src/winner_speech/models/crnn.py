#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time:    2019/9/26 21:29
# @Author:  Mecthew

import numpy as np
import tensorflow as tf
from data_process import extract_melspectrogram_parallel, get_max_length, ohe2cat, pad_seq
from models.my_classifier import Classifier
from tensorflow.python.keras import optimizers
from tensorflow.python.keras.layers import (
    ELU, Convolution2D, CuDNNGRU, Dense, Dropout, Input, MaxPooling2D, Reshape
)
from tensorflow.python.keras.layers.normalization import BatchNormalization
from tensorflow.python.keras.models import Model as TFModel


class CrnnModel(Classifier):
    def __init__(self):
        self.max_length = None

        self._model = None
        self.is_init = False

    def preprocess_data(self, x):
        if self.model_config["common"]["is_cut_audio"]:
            x = [sample[0:self.model_config["common"]["max_audio_duration"] * self.model_config["common"]["audio_sample_rate"]] for sample in x]

        x_mel = extract_melspectrogram_parallel(x,
                                                sr=self.model_config["common"]["sr"],
                                                fft_duration=self.model_config["common"]["fft_duration"],
                                                hop_duration=self.model_config["common"]["hop_duration"],
                                                n_mels=128, use_power_db=True)
        if self.max_length is None:
            self.max_length = get_max_length(x_mel)
            self.max_length = min(self.model_config["common"]["max_frame_num"], self.max_length)
        x_mel = pad_seq(x_mel, pad_len=self.max_length)
        x_mel = x_mel[:, :, :, np.newaxis]
        return x_mel

    def init_model(self, input_shape, num_classes, model_config, **kwargs):
        freq_axis = 2
        channel_axis = 3
        channel_size = 128
        min_size = min(input_shape[:2])
        melgram_input = Input(shape=input_shape)
        # x = ZeroPadding2D(padding=(0, 37))(melgram_input)
        # x = BatchNormalization(axis=freq_axis, name='bn_0_freq')(x)

        x = Reshape((input_shape[0], input_shape[1], 1))(melgram_input)
        # Conv block 1
        x = Convolution2D(64, 3, 1, padding='same', name='conv1')(x)
        x = BatchNormalization(axis=channel_axis, name='bn1')(x)
        x = ELU()(x)
        x = MaxPooling2D(pool_size=(2, 2), strides=(2, 2), name='pool1')(x)
        x = Dropout(0.1, name='dropout1')(x)

        # Conv block 2
        x = Convolution2D(channel_size, 3, 1, padding='same', name='conv2')(x)
        x = BatchNormalization(axis=channel_axis, name='bn2')(x)
        x = ELU()(x)
        x = MaxPooling2D(pool_size=(3, 3), strides=(3, 3), name='pool2')(x)
        x = Dropout(0.1, name='dropout2')(x)

        # Conv block 3
        x = Convolution2D(channel_size, 3, 1, padding='same', name='conv3')(x)
        x = BatchNormalization(axis=channel_axis, name='bn3')(x)
        x = ELU()(x)
        x = MaxPooling2D(pool_size=(4, 4), strides=(4, 4), name='pool3')(x)
        x = Dropout(0.1, name='dropout3')(x)

        if min_size // 24 >= 4:
            # Conv block 4
            x = Convolution2D(channel_size, 3, 1, padding='same', name='conv4')(x)
            x = BatchNormalization(axis=channel_axis, name='bn4')(x)
            x = ELU()(x)
            x = MaxPooling2D(pool_size=(4, 4), strides=(4, 4), name='pool4')(x)
            x = Dropout(0.1, name='dropout4')(x)

        x = Reshape((-1, channel_size))(x)

        gru_units = 128
        if num_classes > gru_units:
            gru_units = int(num_classes * 1.5)
        # GRU block 1, 2, output
        x = CuDNNGRU(gru_units, return_sequences=True, name='gru1')(x)
        x = CuDNNGRU(gru_units, return_sequences=False, name='gru2')(x)
        # x = Dense(max(int(num_classes*1.5), 128), activation='relu', name='dense1')(x)
        x = Dropout(0.3)(x)
        outputs = Dense(num_classes, activation='softmax', name='output')(x)

        self.model_config = model_config

        model = TFModel(inputs=melgram_input, outputs=outputs)
        optimizer = optimizers.Adam(
            lr = self.model_config["optimizer"]["lr"],
            beta_1 = self.model_config["optimizer"]["beta_1"],
            beta_2 = self.model_config["optimizer"]["beta_2"],
            epsilon = self.model_config["optimizer"]["epsilon"],
            decay = self.model_config["optimizer"]["decay"],
            amsgrad = self.model_config["optimizer"]["amsgrad"]
        )
        model.compile(
            optimizer=optimizer, loss="sparse_categorical_crossentropy", metrics=['accuracy']
        )
        model.summary()
        self._model = model
        self.is_init = True

    def fit(self, train_x, train_y, validation_data_fit, round_num, **kwargs):
        val_x, val_y = validation_data_fit
        if round_num >= 2:
            epochs = 10
        else:
            epochs = 8
        patience = 2
        callbacks = [tf.keras.callbacks.EarlyStopping(monitor='val_loss', patience=patience)]
        self._model.fit(
            train_x,
            ohe2cat(train_y),
            epochs=epochs,
            callbacks=callbacks,
            validation_data=(val_x, ohe2cat(val_y)),
            verbose=1,  # Logs once per epoch.
            batch_size=32,
            shuffle=True
        )

    def predict(self, x_test, batch_size=32):
        return self._model.predict(x_test, batch_size=batch_size)
