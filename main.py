import torch
from torch.utils.data import DataLoader
import torchvision.transforms as transforms
from torch.autograd import Variable
import torch.nn as nn
import torch.optim as optim
from math import log10
import argparse
import numpy as np
import copy
import time
import os
import shutil
import torchvision.utils as vutils
from tensorboardX import SummaryWriter
from dataset import ObfuscatedDatasetLoader
from models.baseline_cnn_model import BaselineCNNModel 
from models.resnet_subpixel_cnn import ResnetSubPixelCNN
from scripts.metrics import calc_psnr
from scripts.average_meter import AverageMeter
from scripts.plots import plot_training_loss, plot_train_val_psnr
from loss import create_loss_model
from torchvision import models

def train(train_loader, model, loss_type, optimizer, epoch, model_name, vgg_loss=None):
	""" Train the model for one epoch """

	batch_time_meter = AverageMeter()
	losses_meter = AverageMeter()
	psnr_meter = AverageMeter()

	# set the model to train mode
	model.train()

	# setup the loss function (MSE)
	loss_fn = nn.MSELoss().cuda()

	start = time.time()
	for iteration, batch in enumerate(train_loader, 1):
		input, target = Variable(batch[0]), Variable(batch[1], requires_grad=False)

		# use the GPU
		if use_cuda:
			input = input.cuda()
			target = target.cuda()

		# compute output from CNN model
		output = model(input)

		# calculate the loss (pixel or perceptual)
		if loss_type == "perceptual":
			vgg_loss_output = vgg_loss(output)
			vgg_loss_target = vgg_loss(target)
			loss = loss_fn(vgg_loss_output, vgg_loss_target)
		elif loss_type == "pixel":
			loss = loss_fn(output, target)
		elif loss_type == "pixel_perceptual":
			vgg_loss_output = vgg_loss(output)
			vgg_loss_target = vgg_loss(target)
			perceptual_loss = loss_fn(vgg_loss_output, vgg_loss_target)
			pixel_loss = loss_fn(output, target)
			loss = (.5) * pixel_loss + perceptual_loss

		# measure psnr and loss
		mse = loss_fn(output, target)
		psnr = 10 * log10(255.0 / mse.data[0])
		psnr_meter.update(psnr, input.size(0))
		losses_meter.update(loss.data[0], input.size(0))

		# zero out the gradients
		optimizer.zero_grad()
		loss.backward()
		optimizer.step()

		# measure the time it takes to train for one epoch
		batch_time_meter.update(time.time() - start)
		start = time.time()

		if iteration % 500 == 0:
			
			new_output_dir = "./images_from_runs/{0}/train/".format(model_name)

			if not os.path.exists(new_output_dir):
				os.makedirs(new_output_dir)

			model_output_image = output.data.float()
			model_input_image = input.data.float()
			model_target_image = target.data.float()

			if opt.save_img:
				filename = new_output_dir + "{0}_epoch_{1}_iter.jpg".format(epoch, iteration)
				save_image(input=model_input_image, output=model_output_image, target=model_target_image, filename=filename)
				
			print('Epoch: [{0}][{1}/{2}]\t'
					'Time {batch_time.val:.3f} ({batch_time.avg:.3f})\t'
					'Loss {loss.val:.4f} ({loss.avg:.4f})\t'
					'PSNR {psnr.val:.3f} ({psnr.avg:.3f})'.format(
				epoch, iteration, len(train_loader), batch_time=batch_time_meter,
				loss=losses_meter, psnr=psnr_meter))

	# log value to tensorboard or visdom
	if opt.tensorboard:
		writer.add_scalar("PSNR/train ", psnr_meter.avg, epoch)
		writer.add_scalar("Loss/train", losses_meter.avg, epoch)

def validate(val_loader, model, loss_type, epoch, model_name, vgg_loss=None):
	""" Validate the model on the validation set """
	batch_time_meter = AverageMeter()
	losses_meter = AverageMeter()
	psnr_meter = AverageMeter()

	# switch to eval mode
	model.eval()

	start = time.time() 	

	loss_fn = nn.MSELoss().cuda()

	for iteration, batch in enumerate(val_loader, start=1):
		input, target = Variable(batch[0], volatile=True), Variable(batch[1], volatile=True)

		# use the GPU
		if use_cuda:
			input = input.cuda()
			target = target.cuda()

		# compute output from CNN model
		output = model(input)

		# calculate the loss (pixel or perceptual)
		if loss_type == "perceptual":
			vgg_loss_input = vgg_loss(output.cuda())
			vgg_loss_target = vgg_loss(target.cuda())
			loss = loss_fn(vgg_loss_input, vgg_loss_target)
		elif loss_type == "pixel":
			loss = loss_fn(output, target)
		elif loss_type == "pixel_perceptual":
			vgg_loss_output = vgg_loss(output)
			vgg_loss_target = vgg_loss(target)
			perceptual_loss = loss_fn(vgg_loss_output, vgg_loss_target)
			pixel_loss = loss_fn(output, target)
			loss = (.5) * pixel_loss + perceptual_loss

		# compute the psnr and loss on the validation set
		mse = loss_fn(output , target)
		psnr = 10 * log10(255.0 / mse.data[0])
		psnr_meter.update(psnr, input.size(0))
		losses_meter.update(loss.data[0], input.size(0))

		# measure time
		batch_time_meter.update(time.time() - start)
		start = time.time()

		if iteration % 100 == 0:
			
			new_output_dir = "./images_from_runs/{0}/val/".format(model_name)

			if not os.path.exists(new_output_dir):
				os.makedirs(new_output_dir)

			model_output_image = output.data.float()
			model_input_image = input.data.float()
			model_target_image = target.data.float()

			if opt.save_img:
				filename = new_output_dir + "{0}_epoch_{1}_iter.jpg".format(epoch, iteration)
				save_image(input=model_input_image, output=model_output_image, target=model_target_image, filename=filename)

			print('Test: [{0}/{1}]\t'
					'Time {batch_time.val:.3f} ({batch_time.avg:.3f})\t'
					'Loss {loss.val:.4f} ({loss.avg:.4f})\t'
					'PSNR {psnr.val:.3f} ({psnr.avg:.3f})'.format(
				iteration, len(val_loader), batch_time=batch_time_meter, loss=losses_meter,
				psnr=psnr_meter))

	print("AVG PSNR after epoch {0}: {1}".format(epoch, psnr_meter.avg))

	if opt.tensorboard:
		writer.add_scalar("PSNR/val", psnr_meter.avg, epoch)
		writer.add_scalar("Loss/val", losses_meter.avg, epoch)

	return losses_meter.avg, psnr_meter.avg

def save_image(input, output, target, filename):
	""" Save the input, output, target image during training """
	all_images = torch.cat((input, output, target))
	vutils.save_image(all_images, filename=filename, normalize=True)

def save_checkpoint(name, epoch, model, is_best, filename='checkpoint.pth.tar'):
    """Saves model checkpoint to disk"""
    directory = "saved_models/%s/" % (name)
    if not os.path.exists(directory):
        os.makedirs(directory)
    filename = directory + filename
    torch.save(model, filename)
    if is_best:
        shutil.copyfile(filename, 'saved_models/%s/' % (name) + 'model_best.pth.tar')

def save_model_val_psnr(model, val_psnr):
	""" Save the model psnr values during training to an output file """
	with open("val_psnr_scores/{}.txt".format(model), "w") as f:
		for psnr in val_psnr:
			f.write(str(psnr) + "\n")

if __name__ == "__main__":
	parser = argparse.ArgumentParser(description='Facial Reconstruction using CNNs')
	parser.add_argument("--model", type=str, default="BaselineCNNModel", help="type of model to use for facial reconstruction")
	parser.add_argument("--method", type=str, default="blurred", help="type of obfuscation method to use")
	parser.add_argument("--size", type=int, help="size of the obfuscation method applied to images")
	parser.add_argument('--grayscale', action="store_true", help="use grayscale images?")
	parser.add_argument("--loss", type=str, default="mse", help="type of loss function to use (eg. mse, perceptual)")
	parser.add_argument('--batch_size', type=int, default=64, help='training batch size')
	parser.add_argument('--test_batch_size', type=int, default=10, help='testing batch size')
	parser.add_argument('--epochs', type=int, default=2, help='number of epochs to train for')
	parser.add_argument('--lr', type=float, default=0.01, help='Learning Rate. Default=0.01')
	parser.add_argument('--weight-decay', type=float, default=1e-4, help="weight decay applied to the optimizer")
	parser.add_argument('--cuda', action='store_true', help='use cuda?')
	parser.add_argument('--threads', type=int, default=4, help='number of threads for data loader to use')
	parser.add_argument('--seed', type=int, default=123, help='random seed to use. Default=123')
	parser.add_argument('--tensorboard', action="store_true", help="use tensorboard for visualization?")
	parser.add_argument('--save_img', action="store_true", help="save the output images when training the model")
	parser.add_argument('--num_convblocks', type=int, default=1, help="the number of convblocks to use in the BaselineCNNModel")
	parser.add_argument('--resnet_blocks', type=int, default=5, help="the number of resnet blocks to use the ResnetSubpixelCNN model")
	parser.add_argument('--save_val_psnr', action="store_true", help="store the val_psnr during training in a file?")

	global opt, writer, best_avg_psnr
	opt = parser.parse_args()

	# setup the tensorboard
	writer = SummaryWriter("./runs/") 
	
	best_avg_psnr = 0

	# get the arguments from argparse
	num_epochs = opt.epochs
	lr = opt.lr
	method = opt.method
	size = opt.size
	batch_size = opt.batch_size
	use_cuda = opt.cuda
	loss_type = opt.loss
	num_workers = opt.threads
	weight_decay = opt.weight_decay
	grayscale = opt.grayscale
	num_convblocks = opt.num_convblocks
	resnet_blocks = opt.resnet_blocks
	save_val_psnr = opt.save_val_psnr

	main_hyperparameters = "{0}_method={1}_size={2}_loss={3}_lr={4}_epochs={5}_batch_size={6}".format(opt.model,
																									opt.method,
																									opt.size,
																									opt.loss, opt.lr,
																									opt.epochs,
																									opt.batch_size)
	print "Hyperparameters: "
	print "Model: ", opt.model
	print "Method: ", method
	print "Size: ", size
	print "Loss: ", loss_type
	print "Learning Rate: ", lr
	print "Epochs: ", num_epochs
	print "Batch Size: ", batch_size
	print "\n"

	if grayscale:
		image_color = "grayscale"
	else:
		image_color = "rgb"

	#################
	# Normalization #
	#################
	train_mean = np.array([149.59638197, 114.21029544,  93.41318133])
	train_std = np.array([52.54902009, 44.34252746, 42.88273568])
	normalize = transforms.Normalize(mean=[mean/255.0 for mean in train_mean],
										std=[std/255.0 for std in train_std])

	transform_normalize = transforms.Compose([
		transforms.ToTensor(),
		normalize,
	])

	# get the training data
	train_dset = ObfuscatedDatasetLoader("./data/lfw_preprocessed/cropped_{}/".format(image_color), method, size,
											grayscale=False, data_type="train", transform=transform_normalize)
	train_loader = DataLoader(train_dset, batch_size=batch_size, shuffle=True, num_workers=num_workers)

	# get the validation set
	val_dset = ObfuscatedDatasetLoader("./data/lfw_preprocessed/cropped_{}/".format(image_color), method, size,
										grayscale=False, data_type="val", transform=transform_normalize)
	val_loader = DataLoader(val_dset, shuffle=True, batch_size=batch_size, num_workers=num_workers)

	# get the model
	if opt.model == "BaselineCNNModel": 
		model = BaselineCNNModel(num_convblocks=num_convblocks)
		print "The number of ConvBlocks to use in the BaselineCNNModel: ", num_convblocks
		main_hyperparameters += "_convblocks={}".format(num_convblocks)
	elif opt.model == "ResnetSubPixelCNN":
		model = ResnetSubPixelCNN(num_resnet_blocks=resnet_blocks)
		print "The number of Resnet blocks to use in the ResnetSubPixelCNN model: ", resnet_blocks
		main_hyperparameters += "_resnetblocks={}".format(resnet_blocks)

	# set the optimizer
	optimizer = optim.Adam(model.parameters(), lr=lr, weight_decay=weight_decay)

	# set the scheduler (decay the learning rate every 5 epochs by .1)
	scheduler = optim.lr_scheduler.StepLR(optimizer, step_size=5, gamma=.1) 

	if use_cuda:
		model = model.cuda()

	# Setup the VGG for Perceptual Los
	vgg_loss = None
	if loss_type == "perceptual" or loss_type == "pixel_perceptual":
		vgg16 = models.vgg16(pretrained=True).features
		vgg16.cuda()
		vgg_loss = create_loss_model(vgg16, 8, use_cuda=True)

		for param in vgg_loss.parameters():
			param.requires_grad = False

	val_psnrs = []

	for epoch in range(num_epochs):

		# trains the model for one epoch
		train(train_loader, model, loss_type, optimizer, epoch, model_name=main_hyperparameters, vgg_loss=vgg_loss)

		# evaluate on the validation set
		val_loss, val_psnr_avg = validate(val_loader, model, loss_type, epoch, model_name=main_hyperparameters, vgg_loss=vgg_loss)

		val_psnrs.append(val_psnr_avg)

		# adjust the learning rate if val loss stops improving
		scheduler.step(val_loss)

		# remember the best psnr value and save the checkpoint model
		is_best = val_psnr_avg > best_avg_psnr
		best_avg_psnr = max(val_psnr_avg, best_avg_psnr)

		save_checkpoint(main_hyperparameters, epoch+1, model, is_best)

	# save the val psnr to a file
	save_model_val_psnr(main_hyperparameters, val_psnrs)

	print("Best PSNR on the validation set: {}".format(best_avg_psnr))