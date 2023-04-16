# -*- coding: utf-8 -*-
"""Model & unsupervised training & testing.ipynb

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/1mPLXc1HVEN4bT68UJUuRyOtxVJ3vAAxm
"""

# authenticate user
from google.colab import auth
auth.authenticate_user()

# import packages
import tensorflow as tf
import pandas as pd
import numpy as np
import keras
import matplotlib.pyplot as plt
from tensorflow.keras.preprocessing.image 
import ImageDataGenerator

# authenticate earth engine 
import ee
ee.Authenticate()
ee.Initialize()

# authenticate google colaboratory  
from google.colab import auth
auth.authenticate_user()

!echo "deb http://packages.cloud.google.com/apt gcsfuse-bionic main" > /etc/apt/sources.list.d/gcsfuse.list
!curl https://packages.cloud.google.com/apt/doc/apt-key.gpg | apt-key add -
!apt -qq update
!apt -qq install gcsfuse

!mkdir googleBucketFolder
!gcsfuse --implicit-dirs colab-connect-bucket googleBucketFolder

# define buckets and feature bands
USER_NAME = 'BAMBOT'
OUTPUT_BUCKET = 'BAMBUCKET'
L8SR = ee.ImageCollection('LANDSAT/LC08/C01/T1_SR')
BANDS = ['B2', 'B3', 'B4', 'B5', 'B6', 'B7']
LABEL_DATA = ee.FeatureCollection('projects/google/demo_landcover_labels')
LABEL = 'landcover'
N_CLASSES = 3

FEATURE_NAMES = list(BANDS)
FEATURE_NAMES.append(LABEL)

TRAIN_FILE_PREFIX = 'Training_demo'
TEST_FILE_PREFIX = 'Testing_demo'
file_extension = '.tfrecord.gz'
TRAIN_FILE_PATH = 'gs://' + OUTPUT_BUCKET + '/' + TRAIN_FILE_PREFIX + file_extension
TEST_FILE_PATH = 'gs://' + OUTPUT_BUCKET + '/' + TEST_FILE_PREFIX + file_extension
IMAGE_FILE_PREFIX = 'Image_pixel_demo_'
OUTPUT_IMAGE_FILE = 'gs://' + OUTPUT_BUCKET + '/Classified_pixel_demo.TFRecord'

EXPORT_REGION = ee.Geometry.Rectangle([-122.7, 37.3, -121.8, 38.00])
OUTPUT_ASSET_ID = 'users/' + USER_NAME + '/Classified_pixel_demo'

# define masking function
def maskL8sr(image):
  cloudShadowBitMask = ee.Number(2).pow(3).int()
  cloudsBitMask = ee.Number(2).pow(5).int()
  qa = image.select('pixel_qa')
  mask = qa.bitwiseAnd(cloudShadowBitMask).eq(0).And(
    qa.bitwiseAnd(cloudsBitMask).eq(0))
  return image.updateMask(mask).select(BANDS).divide(10000)

image = L8SR.filterDate('2021-01-01', '2021-12-31').map(maskL8sr).median()

mapid = image.getMapId({'bands': ['B4', 'B3', 'B2'], 'min': 0, 'max': 0.3})
map = folium.Map(location=[40, -80])

folium.TileLayer(
    tiles=mapid['tile_fetcher'].url_format,
    attr='Map Data © Google Earth Engine',
    overlay=True,
    name='median composite',
  ).add_to(map)
map.add_child(folium.LayerControl())
map

# define sampling region
sample = image.sampleRegions(
  collection=LABEL_DATA, properties=[LABEL], scale=20).randomColumn()

training = sample.filter(ee.Filter.lt('random', 0.7))
testing = sample.filter(ee.Filter.gte('random', 0.7))

from pprint import pprint

pprint({'training': training.first().getInfo()})
pprint({'testing': testing.first().getInfo()})

# define training and testing tasks
training_task = ee.batch.Export.table.toCloudStorage(
  collection=training,
  description='Training Export',
  fileNamePrefix=TRAIN_FILE_PREFIX,
  bucket=OUTPUT_BUCKET,
  fileFormat='TFRecord',
  selectors=FEATURE_NAMES)

testing_task = ee.batch.Export.table.toCloudStorage(
  collection=testing,
  description='Testing Export',
  fileNamePrefix=TEST_FILE_PREFIX,
  bucket=OUTPUT_BUCKET,
  fileFormat='TFRecord',
  selectors=FEATURE_NAMES)
  
# start training task
training_task.start()
testing_task.start()
pprint(ee.batch.Task.list())

image_export_options = {
  'patchDimensions': [256, 256],
  'maxFileSize': 104857600,
  'compressed': True
}

image_task = ee.batch.Export.image.toCloudStorage(
  image=image,
  description='Image Export',
  fileNamePrefix=IMAGE_FILE_PREFIX,
  bucket=OUTPUT_BUCKET,
  scale=30,
  fileFormat='TFRecord',
  region=EXPORT_REGION.toGeoJSON()['coordinates'],
  formatOptions=image_export_options,
)

image_task.start()
pprint(ee.batch.Task.list())
pprint(ee.batch.Task.list())

train_dataset = tf.data.TFRecordDataset(TRAIN_FILE_PATH, compression_type='GZIP')
columns = [
  tf.io.FixedLenFeature(shape=[1], dtype=tf.float32) for k in FEATURE_NAMES
]

features_dict = dict(zip(FEATURE_NAMES, columns))

pprint(features_dict)

print(train_dataset)

# add NDVI
input_dataset = parsed_dataset.map(add_NDVI)

# convert input to tuples for keras processing
def to_tuple(inputs, label):
  return (tf.transpose(list(inputs.values())),
          tf.one_hot(indices=label, depth=N_CLASSES))

# Map the to_tuple function, shuffle and batch
input_dataset = input_dataset.map(to_tuple).batch(8)

# construct the model
model = keras.Sequential()

# Convolutional layer & maxpool layer 1
model.add(keras.layers.Conv2D(32,(3,3),activation='relu',input_shape=(100,100,3)))
model.add(keras.layers.MaxPool2D(2,2))

# Convolutional layer & maxpool layer 2
model.add(keras.layers.Conv2D(64,(3,3),activation='relu'))
model.add(keras.layers.MaxPool2D(2,2))

# Convolutional layer & maxpool layer 3
model.add(keras.layers.Conv2D(128,(3,3),activation='relu'))
model.add(keras.layers.MaxPool2D(2,2))

# Convolutional layer & maxpool layer 4
model.add(keras.layers.Conv2D(128,(3,3),activation='relu'))
model.add(keras.layers.MaxPool2D(2,2))

# Flattening the resulting image array to 1-D array
model.add(keras.layers.Flatten())

# 'Hidden' layer with 512 neurons and Rectified Linear Unit activation function 
model.add(keras.layers.Dense(512,activation='relu'))

# Output layer with single neuron which produces 0 for BAM or 1 for NOBAM 
# Sigmoid activation function ensures model output is between 0 and 1
model.add(keras.layers.Dense(1,activation='sigmoid'))

model.compile(loss='categorical_crossentropy', optimizer='adam')

# define test dataset
test_dataset = (
  tf.data.TFRecordDataset(TEST_FILE_PATH, compression_type='GZIP')
    .map(parse_tfrecord, num_parallel_calls=5)
    .map(add_NDVI)
    .map(to_tuple)
    .batch(1))

# evaulate model on test dataset
model.evaluate(test_dataset)

# get a list of all the files in the output bucket
files_list = !gsutil ls 'gs://'{OUTPUT_BUCKET}
# get only the files generated by the image export
exported_files_list = [s for s in files_list if IMAGE_FILE_PREFIX in s]

# get the list of image files and the JSON mixer file
image_files_list = []
json_file = None
for f in exported_files_list:
  if f.endswith('.tfrecord.gz'):
    image_files_list.append(f)
  elif f.endswith('.json'):
    json_file = f

image_files_list.sort()

pprint(image_files_list)
print(json_file)

# use json to create patches and evaluate results
import json
json_text = !gsutil cat {json_file}
mixer = json.loads(json_text.nlstr)
pprint(mixer)

# create patches
patch_width = mixer['patchDimensions'][0]
patch_height = mixer['patchDimensions'][1]
patches = mixer['totalPatches']
patch_dimensions_flat = [patch_width * patch_height, 1]

image_columns = [
  tf.io.FixedLenFeature(shape=patch_dimensions_flat, dtype=tf.float32) 
    for k in BANDS
]

image_features_dict = dict(zip(BANDS, image_columns))

image_dataset = tf.data.TFRecordDataset(image_files_list, compression_type='GZIP')

# parsing function
def parse_image(example_proto):
  return tf.io.parse_single_example(example_proto, image_features_dict)

image_dataset = image_dataset.map(parse_image, num_parallel_calls=5)

image_dataset = image_dataset.flat_map(
  lambda features: tf.data.Dataset.from_tensor_slices(features)
)

image_dataset = image_dataset.map(
  lambda features: add_NDVI(features, None)[0]
)

image_dataset = image_dataset.map(
  lambda data_dict: (tf.transpose(list(data_dict.values())), )
)

image_dataset = image_dataset.batch(patch_width * patch_height)

predictions = model.predict(image_dataset, steps=patches, verbose=1)

print(predictions[0])
print('Writing to file ' + OUTPUT_IMAGE_FILE)

# to instantiate 
writer = tf.io.TFRecordWriter(OUTPUT_IMAGE_FILE)

patch = [[], [], [], []]
cur_patch = 1
for prediction in predictions:
  patch[0].append(tf.argmax(prediction, 1))
  patch[1].append(prediction[0][0])
  patch[2].append(prediction[0][1])
  patch[3].append(prediction[0][2])
  
    if (len(patch[0]) == patch_width * patch_height):
    print('Done with patch ' + str(cur_patch) + ' of ' + str(patches) + '...')
    # create example
    example = tf.train.Example(
      features=tf.train.Features(
        feature={
          'prediction': tf.train.Feature(
              int64_list=tf.train.Int64List(
                  value=patch[0])),
          'urban': tf.train.Feature(
              float_list=tf.train.FloatList(
                  value=patch[1])),
          'vegetation': tf.train.Feature(
              float_list=tf.train.FloatList(
                  value=patch[2])),
          'water': tf.train.Feature(
              float_list=tf.train.FloatList(
                  value=patch[3])),
        }
      )
    )
    # write the example to the file
    writer.write(example.SerializeToString())
    patch = [[], [], [], []]
    cur_patch += 1

writer.close()

!gsutil ls -l {OUTPUT_IMAGE_FILE}

print('Uploading to ' + OUTPUT_ASSET_ID)

!earthengine upload image --asset_id={OUTPUT_ASSET_ID} --pyramiding_policy=mode {OUTPUT_IMAGE_FILE} {json_file}

ee.batch.Task.list()

# map output
predictions_image = ee.Image(OUTPUT_ASSET_ID)

prediction_vis = {
  'bands': 'prediction',
  'min': 0,
  'max': 2,
  'palette': ['red', 'green', 'blue']
}
probability_vis = {'bands': ['urban', 'vegetation', 'water'], 'max': 0.5}

prediction_map_id = predictions_image.getMapId(prediction_vis)
probability_map_id = predictions_image.getMapId(probability_vis)

map = folium.Map(location=[37.6413, -122.2582])
folium.TileLayer(
  tiles=prediction_map_id['tile_fetcher'].url_format,
  attr='Map Data © Google Earth Engine',
  overlay=True,
  name='prediction',
).add_to(map)
folium.TileLayer(
  tiles=probability_map_id['tile_fetcher'].url_format,
  attr='Map Data © Google Earth Engine',
  overlay=True,
  name='probability',
).add_to(map)
map.add_child(folium.LayerControl())
map