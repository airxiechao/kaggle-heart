from default import *

import theano.tensor as T
import objectives

from lasagne.layers.dnn import Conv2DDNNLayer as ConvLayer
from lasagne.layers.dnn import MaxPool2DDNNLayer as MaxPoolLayer
from lasagne.layers import InputLayer
from lasagne.layers import reshape
from lasagne.layers import DenseLayer
from postprocess import upsample_segmentation
from volume_estimation_layers import GaussianApproximationVolumeLayer
import theano_printer

validate_every = 100
validate_train_set = False
save_every = 100
restart_from_save = False

batches_per_chunk = 1

batch_size = 2
sunny_batch_size = 4
num_chunks_train = 8400

image_size = 64

learning_rate_schedule = {
    0:   0.0003,
    250:  0.00003,
    5000: 0.000003,
    8000: 0.0000003,
}

data_sizes = {
    "sliced:data:ax": (batch_size, 30, 15, image_size, image_size), # 30 time steps, 30 mri_slices, 100 px wide, 100 px high,
    "sliced:data:shape": (batch_size, 2,),
    "sunny": (sunny_batch_size, 1, image_size, image_size)
    # TBC with the metadata
}

augmentation_params = {
    "rotation": (0, 360),
    "shear": (-10, 10),
    "translation": (-8, 8),
}


def build_model():

    ###############
    # Sunny model #
    ###############
    l0_sunny = InputLayer(data_sizes["sunny"])

    l1a_sunny = ConvLayer(l0_sunny, num_filters=32, filter_size=(3, 3),
                    pad='same',
                    W=lasagne.init.Orthogonal(),
                    b=lasagne.init.Constant(0.1),
                    )
    l1b_sunny = ConvLayer(l1a_sunny, num_filters=32, filter_size=(3, 3),
                    pad='same',
                    W=lasagne.init.Orthogonal(),
                    b=lasagne.init.Constant(0.1),
                    )
    l1c_sunny = ConvLayer(l1b_sunny, num_filters=32, filter_size=(3, 3),
                    pad='same',
                    W=lasagne.init.Orthogonal(),
                    b=lasagne.init.Constant(0.1),
                    )
    l1d_sunny = ConvLayer(l1c_sunny, num_filters=1, filter_size=(1, 1),
                    pad='same',
                    W=lasagne.init.Orthogonal(),
                    b=lasagne.init.Constant(0.1),
                    nonlinearity=lasagne.nonlinearities.sigmoid)

    #l_sunny_segmentation = lasagne.layers.reshape(l1d_sunny, data_sizes["sunny"][:1] + l1d_sunny.output_shape[-2:])
    l_sunny_segmentation = lasagne.layers.SliceLayer(l1d_sunny, indices=0, axis=1)

    #################
    # Regular model #
    #################
    l0 = InputLayer(data_sizes["sliced:data:ax"])
    l0r = reshape(l0, (-1, 1, ) + data_sizes["sliced:data:ax"][-2:])

    # first do the segmentation steps
    l1a = ConvLayer(l0r, num_filters=32, filter_size=(3, 3),
                    pad='same',
                    W=l1a_sunny.W,
                    b=l1a_sunny.b)
    l1b = ConvLayer(l1a, num_filters=32, filter_size=(3, 3),
                    pad='same',
                    W=l1b_sunny.W,
                    b=l1b_sunny.b)
    l1c = ConvLayer(l1b, num_filters=32, filter_size=(3, 3),
                    pad='same',
                    W=l1c_sunny.W,
                    b=l1c_sunny.b)
    l1d = ConvLayer(l1c, num_filters=1, filter_size=(1, 1),
                    pad='same',
                    W=l1d_sunny.W,
                    b=l1d_sunny.b,
                    nonlinearity=lasagne.nonlinearities.sigmoid)

    l_1r = reshape(l1d, data_sizes["sliced:data:ax"])

    # returns (batch, time, 600) of probabilities
    # TODO: it should also take into account resolution, etc.
    volume_layer = GaussianApproximationVolumeLayer(l_1r)

    # then use max and min over time for systole and diastole
    l_systole = lasagne.layers.FlattenLayer(
                    lasagne.layers.FeaturePoolLayer(volume_layer,
                                                pool_size=volume_layer.output_shape[1],
                                                axis=1,
                                                pool_function=T.min), outdim=2)

    l_diastole = lasagne.layers.FlattenLayer(
                    lasagne.layers.FeaturePoolLayer(volume_layer,
                                                pool_size=volume_layer.output_shape[1],
                                                axis=1,
                                                pool_function=T.max), outdim=2)

    return {
        "inputs":{
            "sliced:data:ax": l0,
            "sunny": l0_sunny,
        },
        "outputs":{
            "systole": l_systole,
            "diastole": l_diastole,
            "segmentation": l_sunny_segmentation,
        }
    }


def build_objective(l_ins, l_outs):
    return objectives.MixedKaggleSegmentationObjective(l_outs)

