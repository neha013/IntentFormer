
import time
import pickle
import json

from utils import *
import tensorflow as tf
from PIL import Image, ImageDraw
from keras.layers import Input, Concatenate, Dense
from keras.layers import GRU
from keras.models import Model, load_model
from keras.applications import vgg16
# from keras.optimizers import adam_v2
from keras import regularizers
from keras_preprocessing.image import img_to_array, load_img
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score
from sklearn.metrics import roc_auc_score, roc_curve, precision_recall_curve
import numpy as np
import os


class PREPROCESS(object):
    """
     An encoder decoder model for pedestrian trajectory prediction

     Attributes:
        _num_hidden_units: Number of LSTM hidden units
        _regularizer_value: The value of L2 regularizer for training
        _regularizer: Training regularizer set as L2
        self._global_pooling: The pulling method for visual features. Options are: 'avg', 'max', 'none' (will return
                              flattened output

     Methods:
        load_images_crop_and_process: Reads the images and generate feature suquences for training
        get_poses: gets the poses for PIE dataset
        flip_pose: Flips the pose joint coordinates
        get_data_sequence: Generates data sequences
        get_data_sequence_balance: Generates data sequences and balances positive and negative samples by augmentations
        get_data: Receives the data sequences generated by the dataset interface and returns train/test data according
                  to model specifications.
        log_configs: Writes model and training configurations to a file
        train: Trains the model
        test: Tests the model
        stacked_rnn: Generates the network model
        _gru: A helper function for creating a GRU unit
     """
    def __init__(self,
                 num_hidden_units=256,
                 global_pooling='avg',
                 regularizer_val=0.0001):

        # Network parameters
        self._num_hidden_units = num_hidden_units
        self._regularizer_value = regularizer_val
        self._regularizer = regularizers.l2(regularizer_val)
        self._global_pooling = global_pooling

    # Processing images anf generate features
    def load_images_crop_and_process(self, img_sequences, bbox_sequences,
                                     ped_ids, save_path,
                                     data_type='train',
                                     crop_type='none',
                                     crop_mode='warp',
                                     crop_resize_ratio=2,
                                     regen_data=False):
        """
        Generate visual feature seuqences by reading and processing images
        :param img_sequences: Sequences of image names
        :param bbox_sequences: Sequences of bounding boxes
        :param ped_ids: Sequences of pedestrian ids
        :param save_path: The path to save the features
        :param data_type: Whether data is for training or testing
        :param crop_type: The method to crop the bounding boxes from the images
                          Options: 'bbox' crops using bounding box coordinats
                                   'context' crops using an enlarged ratio (specified
                                             by 'crop_resize_ratio') of
                                             bounding box coordinates
                                   'surround' similar to context with the difference of
                                              suppressing (by setting to gray value) areas
                                              within the original bounding box coordinate

        :param crop_mode: How the cropped image resized and padded to match the input of
                          processing network. Options are 'warp', 'same', 'pad_same',
                          'pad_resize', 'pad_fit' (see utils.py:img_pad() for more details)
        :param crop_resize_ratio: The ratio by which the image is enlarged to capture the context
                                  Used by crop types 'context' and 'surround'.
        :param regen_data: Whether regenerate the currently saved data.
        :return: Sequences of visual features
        """
        # load the feature files if exists
        print("Generating {} features crop_type={} crop_mode={}\
              \nsave_path={}, ".format(data_type, crop_type, crop_mode,
              save_path))
        convnet = tf.keras.applications.efficientnet.EfficientNetB4(input_shape=(224, 224, 3),
                              include_top=False, weights='imagenet')
        
      
        sequences = []
        bbox_seq = bbox_sequences.copy()
        i = -1
        for seq, pid in zip(img_sequences, ped_ids):
            i += 1
            update_progress(i / len(img_sequences))
            img_seq = []
            prev_img_save_path=None 
            
            for imp, b, p in zip(seq, bbox_seq[i], pid):
                flip_image = False
               
                set_id = imp.split('/')[-3]
                vid_id = imp.split('/')[-2]
                img_name = imp.split('/')[-1].split('.')[0]
                img_save_folder = os.path.join(save_path, set_id, vid_id)
                if crop_type == 'none':
                    img_save_path = os.path.join(img_save_folder, img_name + '.pkl')
                else:
                    img_save_path = os.path.join(img_save_folder, img_name + '_' + p[0] + '.pkl')
              
                if os.path.exists(img_save_path) and not regen_data:
                    with open(img_save_path, 'rb') as fid:
                        try:
                            img_features = pickle.load(fid)
                        except:
                            img_features = pickle.load(fid, encoding='bytes')
            
                else:    
                    if 'flip' in imp:
                        imp = imp.replace('_flip', '')
                        flip_image = True
                        
                    if crop_type == 'none':
                        img_data = load_img(imp, target_size=(224, 224))
                        if flip_image:
                            img_data = img_data.transpose(Image.FLIP_LEFT_RIGHT)
                    else:
                      
                      try:
                        
                        img_data = load_img(imp)  
                        prev_img_save_path=imp

    
                      except (IOError, SyntaxError) as e:
                        imp = prev_img_save_path
                        img_data = load_img(imp) 
                      except Exception as e:
 
                        imp = prev_img_save_path
                        img_data = load_img(imp)

                        
                      if flip_image:
                          img_data = img_data.transpose(Image.FLIP_LEFT_RIGHT)
                      if crop_type == 'bbox':
                        
                        try:
                          
                          cropped_image = img_data.crop(list(map(int, b[0:4])))
                          
                        except OSError as err:  
                          imp = prev_img_save_path
                          img_data = load_img(imp)

                        img_data = img_pad(cropped_image, mode=crop_mode, size=224)
                        
                        
                      else:
                            raise ValueError('ERROR: Undefined value for crop_type {}!'.format(crop_type))
  
                    image_array = img_to_array(img_data)
                    preprocessed_img = tf.keras.applications.efficientnet.preprocess_input(image_array)
                    expanded_img = np.expand_dims(preprocessed_img, axis=0)
                    img_features = convnet.predict(expanded_img)

                    if not os.path.exists(img_save_folder):
                        os.makedirs(img_save_folder)
                    with open(img_save_path, 'wb') as fid:
                        pickle.dump(img_features, fid, pickle.HIGHEST_PROTOCOL)  
                    img_features = np.squeeze(img_features)
                  
                    img_features = np.average(img_features, axis=0)
                
                    img_features = np.average(img_features, axis=0)
                  
             
                  
                img_seq.append(img_features)
            sequences.append(img_seq)
           
        sequences = np.array(sequences)
        
        return sequences

    
    def get_data_sequence(self, data_raw, obs_length, normalize, time_to_event=0):
        """
        Generates data sequences according to the length of the observation and time to event
        :param data_raw: The data sequences from the dataset
        :param obs_length: Observation length
        :param time_to_event: Time (number of frames) to event
        :param normalize: Whether to normalize the bounding box coordinates
        :return: Processed data sequences
        """
        print('\n#####################################')
        print('Generating raw data')
        print('#####################################')
        d = {'center': data_raw['center'].copy(),
             'box': data_raw['bbox'].copy(),
             'box_org': data_raw['bbox'].copy(),
             'ped_id': data_raw['pid'].copy(),
             'acts': data_raw['activities'].copy(),
             'image': data_raw['image'].copy()}
        try:
            d['speed'] = data_raw['obd_speed'].copy()
        except:
            d['speed'] = data_raw['vehicle_act'].copy()
            print('Jaad dataset does not have speed information')
            print('Vehicle actions are used instead')
        

        for i in range(len(d['box'])):
            d['box'][i] = d['box'][i][- obs_length - time_to_event:-time_to_event]
            d['center'][i] = d['center'][i][- obs_length - time_to_event:-time_to_event]
            if normalize:
                d['box'][i] = np.subtract(d['box'][i][1:], d['box'][i][0]).tolist()
                d['center'][i] = np.subtract(d['center'][i][1:], d['center'][i][0]).tolist()

        if normalize:
            obs_length -= 1

        for k in d.keys():
            if k != 'box' and k != 'center':
                for i in range(len(d[k])):
                    d[k][i] = d[k][i][- obs_length - time_to_event:-time_to_event]
                d[k] = np.array(d[k])
            else:
                d[k] = np.array(d[k])
        d['acts'] = d['acts'][:, 0, :]
        return d

    def get_data_sequence_balance(self, data_raw, obs_length, time_to_event, normalize):
        """
        Generates data sequences according to the length of the observation and time to event.
        The number of positive and negative sequences are balanced. Add flipped version of underrepresented
        sequences and subsamples from the overrepresented samples to match the number of samples.
        :param dataset: The data sequences from the dataset
        :param obs_length: Observation length
        :param time_to_event: Time (number of frames) to event
        :param normalize: Whether to normalize the bounding box coordinates
        :return: Processed data sequences
        """
        print('\n#####################################')
        print('Generating balanced raw data')
        print('#####################################')
        d = {'center': data_raw['center'].copy(),
             'box': data_raw['bbox'].copy(),
             'ped_id': data_raw['pid'].copy(),
             'acts': data_raw['activities'].copy(),
             'image': data_raw['image'].copy()}

        try:
            d['speed'] = data_raw['obd_speed'].copy()
        except:
            d['speed'] = data_raw['vehicle_act'].copy()
            print('Jaad dataset does not have speed information')
            print('Vehicle actions are used instead')

        gt_labels = [gt[0] for gt in d['acts']]
        num_pos_samples = np.count_nonzero(np.array(gt_labels))
        num_neg_samples = len(gt_labels) - num_pos_samples

        # finds the indices of the samples with larger quantity
        if num_neg_samples == num_pos_samples:
            print('Positive and negative samples are already balanced')
        else:
            print('Unbalanced: \t Positive: {} \t Negative: {}'.format(num_pos_samples, num_neg_samples))
            if num_neg_samples > num_pos_samples:
                gt_augment = 1
            else:
                gt_augment = 0

            img_width = data_raw['image_dimension'][0]
            num_samples = len(d['ped_id'])
            for i in range(num_samples):
                if d['acts'][i][0][0] == gt_augment:
                    flipped = d['center'][i].copy()
                    flipped = [[img_width - c[0], c[1]]
                               for c in flipped]
                    d['center'].append(flipped)
                    flipped = d['box'][i].copy()

                    flipped = [np.array([img_width - c[2], c[1], img_width - c[0], c[3]])
                               for c in flipped]
                    d['box'].append(flipped)

                    d['ped_id'].append(data_raw['pid'][i].copy())
                    d['acts'].append(d['acts'][i].copy())
                    flipped = d['image'][i].copy()
                    flipped = [c.replace('.png', '_flip.png') for c in flipped]

                    d['image'].append(flipped)
                    if 'speed' in d.keys():
                        d['speed'].append(d['speed'][i].copy())
            gt_labels = [gt[0] for gt in d['acts']]
            num_pos_samples = np.count_nonzero(np.array(gt_labels))
            num_neg_samples = len(gt_labels) - num_pos_samples
            if num_neg_samples > num_pos_samples:
                rm_index = np.where(np.array(gt_labels) == 0)[0]
            else:
                rm_index = np.where(np.array(gt_labels) == 1)[0]

            # Calculate the difference of sample counts
            dif_samples = abs(num_neg_samples - num_pos_samples)
            # shuffle the indices
            np.random.seed(42)
            np.random.shuffle(rm_index)
            # reduce the number of indices to the difference
            rm_index = rm_index[0:dif_samples]

            # update the data
            for k in d:
                seq_data_k = d[k]
                d[k] = [seq_data_k[i] for i in range(0, len(seq_data_k)) if i not in rm_index]

            new_gt_labels = [gt[0] for gt in d['acts']]
            num_pos_samples = np.count_nonzero(np.array(new_gt_labels))
            print('Balanced:\t Positive: %d  \t Negative: %d\n'
                  % (num_pos_samples, len(d['acts']) - num_pos_samples))

        d['box_org'] = d['box'].copy()

        for i in range(len(d['box'])):
            # d['box'][i] = d['box'][i][- obs_length - time_to_event:-time_to_event]
            # d['center'][i] = d['center'][i][- obs_length - time_to_event:-time_to_event]
            if normalize:
                d['box'][i] = np.subtract(d['box'][i][1:], d['box'][i][0]).tolist()
                d['center'][i] = np.subtract(d['center'][i][1:], d['center'][i][0]).tolist()
        if normalize:
            obs_length -= 1
        for k in d.keys():
            if k != 'box' and k != 'center':
                for i in range(len(d[k])):
                    d[k][i] = d[k][i][- obs_length - time_to_event:-time_to_event]
                try:
                    d[k] = np.array(d[k])
                except ValueError as e:
                    if "inhomogeneous" in str(e).lower():
                      # Inhomogeneous shape detected, print the key and value
                      print(d[k])   
                 
            else:
                
                try:
                    d[k] = np.array(d[k])
                except ValueError as e:
                    if "inhomogeneous" in str(e).lower():
                      # Inhomogeneous shape detected, print the key and value
                      print(d[k])   

        d['acts'] = d['acts'][:, 0, :].copy()
        return d

    def get_model_opts(self, model_opts):
        default_opts =  {'obs_input_type': ['local_box', 'local_context', 'box', 'speed'],
                      'enlarge_ratio': 1.5,
                      'pred_target_type': ['crossing'],
                      'obs_length': 15,
                      'time_to_event': 60,
                      'dataset': 'pie',
                      'normalize_boxes': True}
        default_opts.update(model_opts)
        return default_opts
    def get_data(self, data_raw, model_opts):
        """
        Generates train/test data
        :param data_raw: The sequences received from the dataset interface
        :param model_opts: Model options:
                            'obs_input_type': The types of features to be used for train/test. The order
                                            in which features are named in the list defines at what level
                                            in the network the features are processed. e.g. ['local_context',
                                            pose] would behave different to ['pose', 'local_context']
                            'enlarge_ratio': The ratio (with respect to bounding boxes) that is used for processing
                                           context surrounding pedestrians.
                            'pred_target_type': Learning target objective. Currently only supports 'crossing'
                            'obs_length': Observation length prior to reasoning
                            'time_to_event': Number of frames until the event occurs
                            'dataset': Name of the dataset

        :return: Train/Test data
        """
        data = {}
        data_type_sizes_dict = {}

        model_opts = self.get_model_opts(model_opts)

        obs_length = model_opts['obs_length']
        time_to_event = model_opts['time_to_event']
        dataset = model_opts['dataset']
        eratio = model_opts['enlarge_ratio']
        data_type_keys = sorted(data_raw.keys())

        for k in data_type_keys:
            if k == 'test':
                data[k] = self.get_data_sequence(data_raw[k], obs_length, time_to_event, model_opts['normalize_boxes'])
            else:
                data[k] = self.get_data_sequence_balance(data_raw[k], obs_length, time_to_event, model_opts['normalize_boxes'])
            data[k]['box_org'] = data[k]['box_org']
            data_type_sizes_dict['box_org'] = data[k]['box_org'].shape[1:]
            if 'speed' in data[k].keys():
                data_type_sizes_dict['speed'] = data[k]['speed'].shape[1:]
           
        
            # crop only bounding boxes
            if 'local_box' in model_opts['obs_input_type']:
                print('\n#####################################')
                print('Generating local box %s' % k)
                print('#####################################')
                path_to_local_boxes, _ = get_path(save_folder='local_box',
                                                  dataset=dataset,
                                                  save_root_folder='data/features')
                data[k]['local_box'] = data[k]['image']
                data[k]['local_box'] = self.load_images_crop_and_process(data[k]['image'],
                                                                         data[k]['box_org'], data[k]['ped_id'],
                                                                         data_type=k,
                                                                         save_path=path_to_local_boxes,
                                                                         crop_type='bbox',
                                                                         crop_mode='pad_resize')
                data_type_sizes_dict['local_box'] = data[k]['local_box'].shape[1:]

            if 'seg_box' in model_opts['obs_input_type']:
                print('\n#####################################')
                print('Generating seg box %s' % k)
                print('#####################################')
                path_to_local_boxes, _ = get_path(save_folder='seg_box',
                                                  dataset=dataset,
                                                  save_root_folder='data/features')
                data[k]['seg_box'] = data[k]['image']
                new_path = data[k]['image'].replace("images", "seg_images")
                data[k]['seg_box'] = self.load_images_crop_and_process(new_path,
                                                                         data[k]['box_org'], data[k]['ped_id'],
                                                                         data_type=k,
                                                                         save_path=path_to_local_boxes,
                                                                         crop_type='bbox',
                                                                         crop_mode='pad_resize')
                data_type_sizes_dict['seg_box'] = data[k]['seg_box'].shape[1:]    
            if 'ped_id' in model_opts['obs_input_type']:
                print('\n#####################################')
                print('Generating local box %s' % k)
                print('#####################################')
                path_to_local_boxes, _ = get_path(save_folder='local_box',
                                                  dataset=dataset,
                                                  save_root_folder='data/features')
                data[k]['ped_id'] = data[k]['ped_id']
                data[k]['local_box'] = self.load_images_crop_and_process(data[k]['image'],
                                                                         data[k]['box_org'], data[k]['ped_id'],
                                                                         data_type=k,
                                                                         save_path=path_to_local_boxes,
                                                                         crop_type='bbox',
                                                                         crop_mode='pad_resize')
                data_type_sizes_dict['ped_id'] = data[k]['ped_id'].shape[1:]   
            if 'box' in model_opts['obs_input_type']:
                
                data[k]['box'] = data[k]['box']
                data[k]['local_box'] = self.load_images_crop_and_process(data[k]['image'],
                                                                         data[k]['box_org'], data[k]['ped_id'],
                                                                         data_type=k,
                                                                         save_path=path_to_local_boxes,
                                                                         crop_type='bbox',
                                                                         crop_mode='pad_resize')
                data_type_sizes_dict['box'] = data[k]['box'].shape[1:]        
            
            if 'speed' in model_opts['obs_input_type']:
                data[k]['speed'] = data[k]['speed']
                # data[k]['local_box'] = self.load_images_crop_and_process(data[k]['image'],
                #                                                          data[k]['box_org'], data[k]['ped_id'],
                #                                                          data_type=k,
                #                                                          save_path=path_to_local_boxes,
                #                                                          crop_type='bbox',
                #                                                          crop_mode='pad_resize')
                data_type_sizes_dict['speed'] = data[k]['speed'].shape[1:]
        # Create a empty dict for storing the data
        train_test_data = {}
        data_final_keys = sorted(data.keys())
        for k in data_final_keys:
            train_test_data[k] = []

        # Store the type and size of each image
        data_sizes = []
        data_types = []

        for d_type in model_opts['obs_input_type']:
            for k in data.keys():
                train_test_data[k].append(data[k][d_type])
            data_sizes.append(data_type_sizes_dict[d_type])
            data_types.append(d_type)

        # create the final data file to be returned
        for k in data_final_keys:
            train_test_data[k] = (train_test_data[k], data[k]['acts'])

        return train_test_data, data_types, data_sizes

 
