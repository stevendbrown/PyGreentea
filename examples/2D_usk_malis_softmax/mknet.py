from __future__ import print_function
import sys, os, math
import h5py
import numpy as np
from numpy import float32, int32, uint8, dtype

# Load PyGreentea
# Relative path to where PyGreentea resides
pygt_path = '../..'
sys.path.append(pygt_path)
import pygreentea.pygreentea as pygt

import caffe
from caffe import layers as L
from caffe import params as P
from caffe import to_proto
from pygreentea.pygreentea import metalayers as ML

# Start a network
net = caffe.NetSpec()

# Data input layer
net.data, net.datai = L.MemoryData(dim=[1, 1], ntop=2)
# Label input layer
net.aff_label, net.aff_labeli = L.MemoryData(dim=[1, 2], ntop=2, include=[dict(phase=0)])
# Components label layer 
net.comp_label, net.comp_labeli = L.MemoryData(dim=[1, 2], ntop=2, include=[dict(phase=0, stage='euclid')])
# Affinity label input layer
net.smax_label, net.smax_labeli = L.MemoryData(dim=[1, 1], ntop=2, include=[dict(phase=0)])
# Scale input layer
net.scale, net.scalei = L.MemoryData(dim=[1, 2], ntop=2, include=[dict(phase=0, stage='euclid')])
# Silence the not needed data and label integer values
net.nhood, net.nhoodi = L.MemoryData(dim=[1, 1, 2, 3], ntop=2, include=[dict(phase=0, stage='malis')])

silence_test = L.Silence(net.datai, ntop=0, include=[dict(phase=1)])
silence_euclid = L.Silence(net.datai, net.aff_labeli, net.smax_labeli, net.scalei, ntop=0, include=[dict(phase=0, stage='euclid')])
silence_malis = L.Silence(net.datai, net.aff_labeli, net.comp_labeli, net.smax_labeli, net.nhoodi, ntop=0, include=[dict(phase=0, stage='malis')])

# Bundling together the layers, because they have the same function in different phases / stages!
# This ensures the layers will get the same name and function, with different parameters for each phase / stage.
net.silence = {silence_test, silence_euclid, silence_malis}

# USK-Net metalayer
net.usknet = ML.USKNet(net.data, fmap_start=64, depth=1, fmap_inc_rule = lambda fmaps: int(math.ceil(float(fmaps) * 2)), fmap_dec_rule = lambda fmaps: int(math.ceil(float(fmaps) / 3)), sknetconfs=[None, dict(conv=[[6],[4],[4]], padding=[86], fmap_inc_rule = lambda fmaps: 128, fmap_dec_rule = lambda fmaps: int(math.ceil(float(fmaps) / 2)), fmap_bridge_rule = lambda fmaps: fmaps * 4)])

net.aff_out = L.Convolution(net.usknet, kernel_size=[1, 1], num_output=2, param=[dict(lr_mult=1),dict(lr_mult=2)], weight_filler=dict(type='msra'), bias_filler=dict(type='constant'))
net.smax_out = L.Convolution(net.usknet, kernel_size=[1, 1], num_output=8, param=[dict(lr_mult=1),dict(lr_mult=2)], weight_filler=dict(type='msra'), bias_filler=dict(type='constant'))

# Choose output activation functions
net.aff_pred = L.Sigmoid(net.aff_out, ntop=1, in_place=False)
net.smax_pred = L.Softmax(net.smax_out, ntop=1, in_place=False, include=[dict(phase=1)])

# Choose a loss function and input data, label and scale inputs. Only include it during the training phase (phase = 0)
net.euclid_loss = L.EuclideanLoss(net.aff_pred, net.aff_label, net.scale, ntop=0, include=[dict(phase=0, stage='euclid')])
net.malis_loss = L.MalisLoss(net.aff_pred, net.aff_label, net.comp_label, net.nhood, ntop=0, include=[dict(phase=0, stage='malis')])
net.smax_loss = L.SoftmaxWithLoss(net.smax_out, net.smax_label, ntop=0, include=[dict(phase=0)])

# Fix the spatial input dimensions. Note that only spatial dimensions get modified, the minibatch size
# and the channels/feature maps must be set correctly by the user (since this code can definitely not
# figure out the user's intent). If the code does not seem to terminate, then the issue is most likely
# a wrong number of feature maps / channels in either the MemoryData-layers or the network output.

# This function takes as input:
# - The network
# - A list of other inputs to test (note: the nhood input is static and not spatially testable, thus excluded here)
# - A list of the maximal shapes for each input
# - A list of spatial dependencies; here [-1, 0] means the Y axis is a free parameter, and the X axis should be identical to the Y axis.
pygt.fix_input_dims(net,
                    [net.data, net.aff_label, net.comp_label, net.smax_label, net.scale],
                    max_shapes = [[692,692],[700,700],[700,700],[700,700],[700,700]],
                    shape_coupled = [-1, 0])


protonet = net.to_proto()
protonet.name = 'net';

# Store the network as prototxt
with open(protonet.name + '.prototxt', 'w') as f:
    print(protonet, file=f)
