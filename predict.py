""" Predict images form the train and val set """
import torch
import argparse
import os
import torchvision.utils as vutils
from PIL import Image, ImageFilter
import numpy as np
import torchvision.transforms as transforms
from torch.autograd import Variable

def save_image(input, output, target, filename):
    """ Save the input, output, target image during training """
    all_images = torch.cat((input, output, target))
    vutils.save_image(all_images, filename="saved_models/" + filename, normalize=True)

def apply_gaussian_blur(img, radius):
    """ Apply gaussian blur to an image """
    blur_image = img.filter(ImageFilter.GaussianBlur(radius=radius))
    return blur_image

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='Prediction script to test performance of the model on the testing data')
    parser.add_argument("--model", type=str, help="the trained model to evaluate")
    parser.add_argument("--image", type=str, help="the image passed into the model")
    parser.add_argument('--cuda', action='store_true', help='use cuda?')

    opt = parser.parse_args()
    model_name = opt.model
    use_cuda = opt.cuda
    test_image = opt.image
    clean = Image.open(test_image)
    blurred = apply_gaussian_blur(clean, radius=4)
    if os.path.isfile("saved_models/" + str(model_name) + "model_best.pth.tar"):
        print("=> loading checkpoint '{}'".format(model_name))
        model = torch.load("saved_models/" + str(model_name) + "model_best.pth.tar")
        model.cuda()
        model.eval()

        # convert to cuda
        train_mean = np.array([149.59638197, 114.21029544, 93.41318133])
        train_std = np.array([52.54902009, 44.34252746, 42.88273568])
        normalize = transforms.Normalize(mean=[mean / 255.0 for mean in train_mean],
                                         std=[std / 255.0 for std in train_std])

        transform_normalize = transforms.Compose([
            transforms.ToTensor(),
            normalize,
        ])
        # normalize train_mean and train_std
        blurred = np.array(blurred)
        blurred = Variable(transform_normalize(blurred)) 
        blurred = blurred.unsqueeze(0)

        print "Blurred Input to model: ", blurred.size()
        output = model(blurred.cuda())

        print "Blurred Output Model: ", output.size() 
        
        clean = np.array(clean)
        clean = Variable(transform_normalize(clean)) 
        clean = clean.unsqueeze(0) 

        vutils.save_image(output.data.float(), filename="saved_models/" + str(model_name) + "prediction.jpg", normalize=True)
        vutils.save_image(blurred.data.float(), filename="saved_models/" + str(model_name) + "blurred.jpg", normalize=True)
        vutils.save_image(clean.data.float(), filename="saved_models/" + str(model_name) + "ground_truth.jpg", normalize=True)
 
        # save_image(input=input, output=output, target=target, filename=str(model_name) + "Prediction.jpg")
    else:
        print "no checkpoint found..."