# -*- coding: utf-8 -*-
# @Author: lidong
# @Date:   2018-03-18 13:41:34
# @Last Modified by:   yulidong
# @Last Modified time: 2018-04-12 15:43:29
import sys
import torch
import visdom
import argparse
import numpy as np
import torch.nn as nn
import torch.nn.functional as F
import torchvision.models as models

from torch.autograd import Variable
from torch.utils import data
from tqdm import tqdm

from rsden.models import get_model
from rsden.loader import get_loader, get_data_path
from rsden.metrics import runningScore
from rsden.loss import *
from rsden.augmentations import *
import os


def train(args):

    # Setup Augmentations
    data_aug = Compose([RandomRotate(10),
                        RandomHorizontallyFlip()])

    # Setup Dataloader
    data_loader = get_loader(args.dataset)
    data_path = get_data_path(args.dataset)
    t_loader = data_loader(data_path, is_transform=True,
                           split='train_split', img_size=(args.img_rows, args.img_cols))
    v_loader = data_loader(data_path, is_transform=True,
                           split='test_split', img_size=(args.img_rows, args.img_cols))

    n_classes = t_loader.n_classes
    trainloader = data.DataLoader(
        t_loader, batch_size=args.batch_size, num_workers=8, shuffle=True)
    valloader = data.DataLoader(
        v_loader, batch_size=args.batch_size, num_workers=8)

    # Setup Metrics
    running_metrics = runningScore(n_classes)

    # Setup visdom for visualization
    if args.visdom:
        vis = visdom.Visdom()

        loss_window = vis.line(X=torch.zeros((1,)).cpu(),
                               Y=torch.zeros((1)).cpu(),
                               opts=dict(xlabel='minibatches',
                                         ylabel='Loss',
                                         title='Training Loss',
                                         legend=['Loss']))
        pre_window = vis.image(
            np.random.rand(480, 640),
            opts=dict(title='predict!', caption='predict.'),
        )
        ground_window = vis.image(
            np.random.rand(480, 640),
            opts=dict(title='ground!', caption='ground.'),
        )
    # Setup Model
    model = get_model(args.arch)
    model = torch.nn.DataParallel(
        model, device_ids=range(torch.cuda.device_count()))
    #model = torch.nn.DataParallel(model, device_ids=range(torch.cuda.device_count()))
    model.cuda()

    # Check if model has custom optimizer / loss
    # modify to adam, modify the learning rate
    if hasattr(model.module, 'optimizer'):
        optimizer = model.module.optimizer
    else:
        optimizer = torch.optim.SGD(
            model.parameters(), lr=args.l_rate, momentum=0.99, weight_decay=5e-4)

    if hasattr(model.module, 'loss'):
        print('Using custom loss')
        loss_fn = model.module.loss
    else:
        loss_fn = l1
    trained=0
    scale=100
    if args.resume is not None:
        if os.path.isfile(args.resume):
            print("Loading model and optimizer from checkpoint '{}'".format(args.resume))
            checkpoint = torch.load(args.resume)
            model.load_state_dict(checkpoint['model_state'])
            optimizer.load_state_dict(checkpoint['optimizer_state'])
            print("Loaded checkpoint '{}' (epoch {})"
                  .format(args.resume, checkpoint['epoch']))
            trained=checkpoint['epoch']
            print('load success!')
        else:
            print("No checkpoint found at '{}'".format(args.resume))
            print('Initialize from resnet50!')
            resnet50=torch.load('/home/lidong/Documents/RSDEN/RSDEN/resnet34-333f7ec4.pth')
            model_dict=model.state_dict()            
            pre_dict={k: v for k, v in resnet50.items() if k in model_dict}
            model_dict.update(pre_dict)
            model.load_state_dict(model_dict)
            print('load success!')
    #model_dict=model.state_dict()
    best_error=100
    best_rate=100
    # it should be range(checkpoint[''epoch],args.n_epoch)
    for epoch in range(trained, args.n_epoch):
        print('training!')
        model.train()
        for i, (images, labels) in enumerate(trainloader):
            images = Variable(images.cuda())
            labels = Variable(labels.cuda())

            optimizer.zero_grad()
            outputs = model(images)
            #outputs=outputs
            loss = loss_fn(input=outputs, target=labels)
            # print('training:'+str(i)+':learning_rate'+str(loss.data.cpu().numpy()))
            loss.backward()
            optimizer.step()
            # print(torch.Tensor([loss.data[0]]).unsqueeze(0).cpu())
            if args.visdom:
                vis.line(
                    X=torch.ones(1).cpu() * i,
                    Y=torch.Tensor([loss.data[0]]).unsqueeze(0).cpu()[0],
                    win=loss_window,
                    update='append')
                pre = outputs.data.cpu().numpy().astype('float32')
                pre = pre[0, :, :, :]
                #pre = np.argmax(pre, 0)
                pre = np.reshape(pre, [480, 640]).astype('float32')/np.max(pre)
                #pre = pre/np.max(pre)
                # print(type(pre[0,0]))
                vis.image(
                    pre,
                    opts=dict(title='predict!', caption='predict.'),
                    win=pre_window,
                )
                ground=labels.data.cpu().numpy().astype('float32')
                #print(ground.shape)
                ground = ground[0, :, :]
                ground = np.reshape(ground, [480, 640]).astype('float32')/np.max(ground)
                vis.image(
                    ground,
                    opts=dict(title='ground!', caption='ground.'),
                    win=ground_window,
                )
            # if i%100==0:
            #     state = {'epoch': epoch,
            #              'model_state': model.state_dict(),
            #              'optimizer_state' : optimizer.state_dict(),}
            #     torch.save(state, "training_{}_{}_model.pkl".format(i, args.dataset))
            # if loss.data[0]/weight<100:
            # 	weight=100
            # else if(loss.data[0]/weight<100)
            print("data [%d/291/%d/%d] Loss: %.4f" % (i, epoch, args.n_epoch,loss.data[0]))
        if epoch%10==0:    
            print('testing!')
            model.eval()
            error=[]
            error_rate=[]
            ones=np.ones([480,640])
            zeros=np.zeros([480,640])
            for i_val, (images_val, labels_val) in tqdm(enumerate(valloader)):
                images_val = Variable(images_val.cuda(), requires_grad=False)
                labels_val = Variable(labels_val.cuda(), requires_grad=False)
                with torch.no_grad():
                    outputs = model(images_val)
                    pred = outputs.data.cpu().numpy()
                    gt = labels_val.data.cpu().numpy()
                    pred=np.reshape(pred,[4,480,640])
                    gt=np.reshape(gt,[4,480,640])
                    dis=np.abs(gt-pred)
                    error.append(np.mean(dis))
                    error_rate.append(np.mean(np.where(dis<0.05,ones,zeros)))
            error=np.mean(error)
            error_rate=np.mean(error_rate)
            print("error=%.4f,error < 5 cm : %.4f"%(error,error_rate))
            if error<= best_error:
                best_error = error
                state = {'epoch': epoch+1,
                         'model_state': model.state_dict(),
                         'optimizer_state': optimizer.state_dict(), }
                torch.save(state, "{}_{}_best_model.pkl".format(
                    args.arch, args.dataset))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Hyperparams')
    parser.add_argument('--arch', nargs='?', type=str, default='rsnet',
                        help='Architecture to use [\'region support network\']')
    parser.add_argument('--dataset', nargs='?', type=str, default='nyu1',
                        help='Dataset to use [\'sceneflow and kitti etc\']')
    parser.add_argument('--img_rows', nargs='?', type=int, default=480,
                        help='Height of the input image')
    parser.add_argument('--img_cols', nargs='?', type=int, default=640,
                        help='Width of the input image')
    parser.add_argument('--n_epoch', nargs='?', type=int, default=4000,
                        help='# of the epochs')
    parser.add_argument('--batch_size', nargs='?', type=int, default=4,
                        help='Batch Size')
    parser.add_argument('--l_rate', nargs='?', type=float, default=1e-3,
                        help='Learning Rate')
    parser.add_argument('--feature_scale', nargs='?', type=int, default=1,
                        help='Divider for # of features to use')
    parser.add_argument('--resume', nargs='?', type=str, default=None,
                        help='Path to previous saved model to restart from /home/lidong/Documents/RSDEN/RSDEN/rsnet_nyu1_best_model.pkl')
    parser.add_argument('--visdom', nargs='?', type=bool, default=True,
                        help='Show visualization(s) on visdom | False by  default')
    args = parser.parse_args()
    train(args)
