import os
import random
import torch
from torch.utils.data import random_split, DataLoader from torchvision import transforms
import torch.nn as nn
import torch.optim as optim
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image
from torch.utils.data import Dataset
from torchvision.datasets import ImageFolder
import torch.nn.functional as F
from optparse import OptionParser
from torch import optim
from torch.autograd import Function, Variable
import glob
import pickle
from tqdm import tqdm
from skimage import transform
from copy import deepcopy
from scipy import ndimage, misc

"""Loading the dataset and splitting it to train-val-test sets and matching the images with the corresponding labels:"""

def split_train_val_test(image_paths, mask_paths, train_size, val_size): img_dic = {}
    mask_dic = {}
    len_data = len(image_paths)
    for i in range(len(image_paths)):
      img_dic[os.path.basename(image_paths[i])[:-4]] = image_paths[i]
    for i in range(len(mask_paths)):
      mask_dic[os.path.basename(mask_paths[i])[:-9]] = mask_paths[i]
    combined = []
    for key in img_dic:
        combined.append((img_dic[key], mask_dic[key]))
    len_trian = int(len_data * train_size)
    len_val = int(len_data * val_size)
    train_paths = combined[:len_trian]
    val_paths = combined[len_trian:len_trian + len_val]
    test_paths = combined[len_trian + len_val:]
    return train_paths, val_paths, test_paths

"""read the image and label as a pair, and rescale your input images to a smaller size to speed up training:"""

def preprocess_image(paths): data_list = []
    h2, w2 = 80, 100
    for i in tqdm(range(len(paths))):
      img = np.array(Image.open(paths[i][0]), np.float32) / 255.0
      mask = np.array(Image.open(paths[i][1]), np.uint8)
      rescaled_img = transform.resize(img, (h2, w2), mode='constant',anti_aliasing=True, preserve_range=True)
      rescaled_mask = np.uint8(transform.resize(mask, (h2, w2), mode='constant', anti_aliasing=True, preserve_range=True))
      data_list.append((rescaled_img, rescaled_mask))
      return data_list

image_paths = glob.glob("/home/ne2213/IVP-CA4/PNGImages/*.png")
mask_paths = glob.glob("/home/ne2213/IVP-CA4/PedMasks/*.png")
train_size = 0.8
val_size = 0.1
train_paths, val_paths, test_paths = split_train_val_test(image_paths,mask_paths, train_size, val_size)
train_data = preprocess_image(train_paths)
val_data = preprocess_image(val_paths)
test_data = preprocess_image(test_paths)

"""Applying data augmentation transform:"""

class RandomFlip(object):
  def __init__(self, flip_probability=0.60):
      self.flip_probability = flip_probability

  def __call__(self, sample):
      if random.uniform(0, 1) < self.flip_probability:
          return self.to_tensor(sample)
      else:
          img, label = sample['img'], sample['label']
          img_flipped = img[:, :, ::-1]
          label_flipped = label[:, ::-1]
          flipped_sample = {'img': img_flipped, 'label': label_flipped}
          return self.to_tensor(flipped_sample)

  def to_tensor(self, sample):
      image, label = sample['img'], sample['label']
      return {'img': torch.from_numpy(image.copy()).type(torch.DoubleTensor),
              'label': torch.from_numpy(label.copy()).type(torch.DoubleTensor)}

"""Plot original and augmented images:"""

sample = {'img': train_data[1][0], 'label': train_data[1][1]}
flip_transform = RandomFlip()
augmented_sample = flip_transform(deepcopy(sample))
fig, axs = plt.subplots(1, 2, figsize=(10, 5))
axs[0].imshow(sample['img'])
axs[0].set_title('Original')
axs[1].imshow(augmented_sample['img'].numpy())
axs[1].set_title('Augmented')
plt.show()

"""Implementing a CNN for binary segmentation:"""

class single_conv(nn.Module):
    def __init__(self, in_ch, out_ch):
            super(single_conv, self).__init__()
            self.conv = nn.Sequential(
    nn.Conv2d(in_ch, out_ch, 3, padding=1), nn.BatchNorm2d(out_ch), nn.ReLU(inplace=True))

    def forward(self, x):
      if x.dim() == 3:
        x = x.unsqueeze(0)
      x = self.conv(x)
      return x


class down(nn.Module):
    def __init__(self, in_ch, out_ch):
            super(down, self).__init__()
            self.down = nn.MaxPool2d(kernel_size=2, stride=2) # use nn.MaxPool2d( ) self.conv = single_conv(in_ch, out_ch) # use previously defined single_cov

    def forward(self, x):
      x = self.down(x)
      x = self.conv(x)
      return x


class up(nn.Module):
    def __init__(self, in_ch, out_ch):
            super(up, self).__init__()
            self.up = nn.Upsample(scale_factor=2)
            self.conv = single_conv(in_ch, out_ch)
    def forward(self, x1, x2):
            x1 = self.up(x1)
            diffY = x2.size()[2] - x1.size()[2]
            diffX = x2.size()[3] - x1.size()[3]
            x1 = F.pad(x1, (diffX // 2, diffX - diffX//2, diffY // 2, diffY - diffY//2))
            x = torch.cat([x2, x1], dim=1)
            x = self.conv(x)
            return x

class outconv(nn.Module):
    def __init__(self, in_ch, out_ch):
            super(outconv, self).__init__()
            self.conv = nn.Conv2d(in_ch, out_ch, 3, padding=1)

    def forward(self, x):
      x = self.conv(x)
      return x



class UNet(nn.Module):
    def __init__(self, n_channels, n_classes):
            super(UNet, self).__init__()
            self.inc = single_conv(n_channels, 16)
            self.down1 = down(16, 32)
            self.down2 = down(32, 32)
            self.up1 = up(64, 16)
            self.up2 = up(32, 16)
            self.outc = outconv(16, 1)

    def forward(self, x):
            x1 = self.inc(x)
            x2 = self.down1(x1)
            x3 = self.down2(x2)
            x = self.up1(x3, x2)
            x = self.up2(x, x1)
            x = self.outc(x)
            return F.sigmoid(x)

"""1. single_conv Class:
• Defines a single convolutional block with a 3x3 convolution layer, batch normalization,
5
and ReLU activation.


2. down Class:
• Represents the downsampling block in the U-Net architecture, which consists of max- pooling and a single convolution block. It performs max-pooling followed by the convo- lutional block on the input tensor.


3. up Class:
• Represents the upsampling block in the U-Net architecture, which includes upsampling,
padding, and a single convolution block. It upsamples the input tensor, adjusts the spatial dimensions, concatenates it with a skip connection, and applies the convolutional block.


4. outconv Class:
• Defines the output convolutional block without batch normalization and ReLU activa-
tion, and applies a 3x3 convolutional layer to the input tensor.


5. UNet Class:
• Constructs the U-Net architecture by combining the previously defined blocks. It defines the forward pass by sequentially applying the encoding (downsampling) and decoding (upsampling) blocks, with skip connections. The final output is obtained through the output convolutional block with a sigmoid activation.

training loss, validation loss, and validation DICE curves:


DiceCoefficient Function: Implenemting a function to calculate the intersection and union and
return DICE coefficient.


dice_coeff Function: Computes the average Dice coefficient for a batch of predictions and targets by iterating through pairs of prediction and target tensors using a loop.
"""

class DiceCoefficient(Function):
    def forward(self, prediction, target):
            self.save_for_backward(prediction, target)
            epsilon = 0.0001
            intersection = 2 * torch.sum(prediction * target)
            union = torch.sum(prediction) + torch.sum(target) + epsilon
            dice = intersection / union
    return dice

def dice_coefficient(predictions, targets):
    total_dice = torch.FloatTensor(1).zero_()
    for i, (pred, target) in enumerate(zip(predictions, targets)):
        total_dice = total_dice + DiceCoefficient().forward(prediction=pred,target=target)
    average_dice = total_dice / (i + 1)
    return average_dice

"""CustomDataset Class:

Represents a PyTorch dataset where each sample consists of an image and its corresponding mask:
6


• Retrieves the image and mask at the specified index.


• Transposes the image to have the channel dimension as the first dimension (C, H, W).


• Creates a dictionary (sample) with keys ‘img’ and ‘label’, representing the image and mask, respectively.


• Applies the specified data transformations to the sample and returns the transformed sample.
"""

class CustomDataset(Dataset):
def __init__(self, image_masks, transforms=None):
    self.image_masks = image_masks
    self.transforms = transforms if transforms is not None else []

def __len__(self):
    return len(self.image_masks)

def __getitem__(self, index):
    image = self.image_masks[index][0]
    mask = self.image_masks[index][1]
    image = np.transpose(image, axes=[2, 0, 1])
    sample = {'img': image, 'label': mask}
    for transform in self.transforms.transforms:
        sample = transform(sample)
    return sample

train_dataset = CustomDataset(train_data, transforms=transforms, Compose([RandomFlip()]))
val_dataset = CustomDataset(val_data, transforms=transforms, Compose([RandomFlip()]))
test_dataset = CustomDataset(test_data, transforms=transforms, Compose([RandomFlip()]))

"""eval_net Function:

evaluates a neural network (net) on a dataset and calculates the average Dice coefficient for binary segmentation tasks. It iterates through batches in the provided dataset and passes the input image through the network to obtain the predicted mask (mask_pred). It then calls the (dice_coefficient) function to calculate the Dice coefficient as a measure of the network’s performance on the provided dataset.
"""

def eval_net(net, dataset):
    net.eval()
    total_dice_coeff = 0.0 total_samples = 0
    for batch in dataset:
            img, true_mask = batch['img'], batch['label']
            img = img.unsqueeze(0)
            true_mask = true_mask.unsqueeze(0).unsqueeze(0)
            mask_pred = net(img)
            mask_pred = torch.round(mask_pred)
            total_dice_coeff += dice_coefficient(mask_pred, true_mask)
            total_samples += true_mask.size(0)
            return total_dice_coeff / total_samples

"""Next, I create an instance of the U-Net neural network, and initialize the hyperparameters used in the training proccess.
I also set up an SGD optimizer with specified parameters (learning rate, momentum, weight decay) and use binary cross-entropy loss as the criterion.
"""

net = UNet(n_channels=3, n_classes=1)
net = net.double()
epochs = 50
batch_size = 16
lr = 0.001
N_train = len(train_data)
optimizer = optim.SGD(net.parameters(), lr=lr, momentum=0.9, weight_decay=0. ,0005)
criterion = nn.BCELoss()

"""Next I perform training and validation iterations over the specified number of epochs. For each epoch:


• The code iterates through batches in the training loader (train_loader).


• Extracts input images (imgs) and true masks (true_mask) from each batch.


• Performs a forward pass through the network to obtain predicted masks (mask_pred).


• Computes the loss using the specified loss criterion (criterion), likely binary cross-entropy loss.


• Performs a backward pass and optimization step using the optimizer (optimizer).


• Calculates the average training loss for the epoch.


• Evaluates the network on the validation dataset using the eval_net function and calculates the validation Dice coefficient.
"""

train_loss_values = []
val_loss_values = []
val_dice_values = []

for epoch in range(epochs):
  print('Epoch {}/{}.'.format(epoch + 1, epochs))
  net.train()

  train_loader = torch.utils.data.DataLoader(train_dataset, batch_size=batch_size, shuffle=True)
  val_loader = torch.utils.data.DataLoader(val_dataset, batch_size=batch_size, shuffle=True)
  test_loader = torch.utils.data.DataLoader(test_dataset, batch_size=batch_size, shuffle=True)

  epoch_loss = 0

  for i, batch in enumerate(train_loader):
        imgs, true_mask = batch['img'], batch['label']
        mask_pred = net(imgs.squeeze(0))
        B = imgs.shape[0]
        masks_probs_flat = mask_pred.view(B, -1)
        true_masks_flat = true_mask.view(B, -1)
        true_masks_flat = torch.clamp(true_masks_flat, 0, 1)
        loss = criterion(masks_probs_flat, true_masks_flat)
        epoch_loss += loss.item()
        optimizer.zero_grad()
        loss.backward()
        optimizer.step()

  train_loss = epoch_loss / len(train_loader)
  train_loss_values.append(train_loss)

  print('Train Loss: {}'.format(epoch_loss / i))

  net.eval()
  val_loss = 0.0

  for i, val_batch in enumerate(val_loader):
      val_imgs, val_true_mask = val_batch['img'], val_batch['label']
      val_mask_pred = net(val_imgs.squeeze(0))
      val_B = val_imgs.shape[0]
      val_masks_probs_flat = val_mask_pred.view(val_B, -1)
      val_true_masks_flat = val_true_mask.view(val_B, -1)
      val_true_masks_flat = torch.clamp(val_true_masks_flat, 0, 1)
      val_loss += criterion(val_masks_probs_flat, val_true_masks_flat).item()

  val_loss /= len(val_loader)
  val_loss_values.append(val_loss)
  print('Validation Loss: {:.4f}'.format(val_loss))

  val_dice = eval_net(net, val_dataset)
  val_dice_values.append(val_dice)
  print('Val Dice Coeff: {}'.format(val_dice))

"""Next, I create a visual representation of the training and validation metrics (loss and Dice coefficient) over epochs in a 1x3 grid of subplots:"""

epochs_range = range(1, epochs + 1)

plt.figure(figsize=(12, 4))
plt.subplot(1, 3, 1)
plt.plot(epochs_range, train_loss_values, label='Training Loss')
plt.title('Training Loss')
plt.xlabel('Epoch')
plt.ylabel('Loss')
plt.legend()

plt.subplot(1, 3, 2)
plt.plot(epochs_range, val_loss_values, label='Validation Loss', color='orange')
plt.ylim(0, 1)
plt.title('Validation Loss')
plt.xlabel('Epoch')
plt.ylabel('Loss')
plt.legend()

plt.subplot(1, 3, 3)
val_dice_values_np = [tensor.detach().numpy() for tensor in val_dice_values]
plt.plot(epochs_range, np.array(val_dice_values_np), label='Validation Dice Coeff', color='green')
plt.title('Validation Dice Coeff') plt.xlabel('Epoch') plt.ylabel('Dice Coefficient')
plt.legend()
plt.tight_layout()
plt.show()

"""example segmentations:

Next, I define a function visualize_sample that takes a sample as input and the neural network (net) to visualize the original image, true mask, and the overlay of the original image and predicted mask.

on train data:
"""

def visualize_sample(sample, net=None):
    img = sample['img']
    true_mask = sample['label']
    img_np = img.numpy().transpose(1, 2, 0)
    mask_np = true_mask.numpy().squeeze()
    if net is not None:
      net.eval()

      with torch.no_grad():
        mask_pred = net(img.unsqueeze(0))
        mask_pred = torch.round(mask_pred)

      mask_pred_np = mask_pred.numpy().squeeze()

    plt.figure(figsize=(15, 6))

    plt.subplot(1, 3, 1)
    plt.imshow(img_np)
    plt.title('Original Image')

    plt.subplot(1, 3, 2)
    plt.imshow(mask_np, cmap='gray')
    plt.title('Mask')

    if net is not None:
      plt.subplot(1, 3, 3)
      plt.imshow(img_np * mask_np[:, :, np.newaxis])
      plt.title('Original Image × Predicted Mask')

    plt.show()

sample = train_dataset[0]
visualize_sample(sample, net)

"""example segmentation on an input image not from the FudanPed dataset."""

new_img_path = '/home/ne2213/IVP-CA4/other_image.png'

img = np.array(Image.open(new_img_path), np.float32) / 255.0
h2, w2 = 80, 100

rescaled_img = transform.resize(img, (h2, w2), mode='constant',anti_aliasing=True, preserve_range=True)
new_img = np.transpose(rescaled_img, axes=[2, 0, 1])
new_img = torch.from_numpy(new_img).double()
new_img_tensor = new_img.unsqueeze(0)

net.eval()
with torch.no_grad():
    mask_pred = net(new_img_tensor)
mask_pred = torch.round(mask_pred)
mask_pred_np = mask_pred.numpy().squeeze()

plt.figure(figsize=(15, 6))

plt.subplot(1, 3, 1)
plt.imshow(rescaled_img)
plt.title('Original Image')

plt.subplot(1, 3, 2)
plt.imshow(true_mask_np, cmap='gray')
plt.title('True Mask')

plt.subplot(1, 3, 3)
plt.imshow(img_np * true_mask_np[:, :, np.newaxis])
plt.title('Original Image × Predicted Mask')

plt.show()

"""As it can be seen, the results are not as good. Which means the model doesn’t have a good prediction for the out of distribution image."""
