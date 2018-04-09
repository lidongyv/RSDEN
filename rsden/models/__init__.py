# -*- coding: utf-8 -*-
# @Author: yulidong
# @Date:   2018-03-18 15:24:33
# @Last Modified by:   yulidong
# @Last Modified time: 2018-04-07 15:11:34

import torchvision.models as models

from rsden.models.rsn import *


def get_model(name, n_classes):
    model = _get_model_instance(name)

    model = model(n_classes=n_classes)

    return model

def _get_model_instance(name):
    try:
        return {
            'rsnet': rsn,

        }[name]
    except:
        print('Model {} not available'.format(name))
