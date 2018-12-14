import os
import json
from lib.rpc_model import RPCModel
from lib.height_range import height_range
from lib.gen_grid import gen_grid
from lib.solve_affine import solve_affine
from lib.solve_perspective import solve_perspective
import utm
import numpy as np
import quaternion


class Approx(object):
    def __init__(self, tile_dir):
        self.tile_dir = tile_dir

        # needs to use a common world coordinate frame for all smaller regions
        # common coordinate frame is:
        #   aoi upper-left southing, aoi upper-left easting, aoi upper-left height
        with open(os.path.join(tile_dir, 'aoi.json')) as fp:
            self.aoi_dict = json.load(fp)

        self.img_names = []
        self.rpc_models = []
        self.region_dicts = []

        metas_subdir = os.path.join(self.tile_dir, 'metas/')
        regions_subdir = os.path.join(self.tile_dir, 'regions/')
        for item in os.listdir(metas_subdir):
            self.img_names.append(item[:-5] + '.png')
            with open(os.path.join(metas_subdir, item)) as fp:
                self.rpc_models.append(RPCModel(json.load(fp)))
            with open(os.path.join(regions_subdir, item)) as fp:
                self.region_dicts.append(json.load(fp))

        self.cnt = len(self.rpc_models)

        self.min_height, self.max_height = height_range(self.rpc_models)

    # def approx(self):
    #     self.approx_affine_latlon()
    #     self.approx_perspective_utm()

    def approx_affine_latlon(self):
        affine_dict = {}
        for i in range(self.cnt):
            region_dict = self.region_dicts[i]
            ul_east = region_dict['x']
            ul_north = region_dict['y']
            lr_east = ul_east + region_dict['w']
            lr_north = ul_north - region_dict['h']
            zone_number = region_dict['zone_number']
            zone_letter = region_dict['zone_letter']

            # convert to lat, lon
            ul_lat, ul_lon = utm.to_latlon(ul_east, ul_north, zone_number, zone_letter)
            lr_lat, lr_lon = utm.to_latlon(lr_east, lr_north, zone_number, zone_letter)

            # create grid
            lat_points = np.linspace(ul_lat, lr_lat, 20)
            lon_points = np.linspace(ul_lon, lr_lon, 20)
            z_points = np.linspace(self.min_height, self.max_height, 20)

            xx, yy, zz = gen_grid(lat_points, lon_points, z_points)

            col, row = self.rpc_models[i].projection(xx, yy, zz)

            keep_mask = np.logical_and(col >= 0, row >= 0)
            keep_mask = np.logical_and(keep_mask, col < self.rpc_models[i].width)
            keep_mask = np.logical_and(keep_mask, row < self.rpc_models[i].height)
            P = solve_affine(xx, yy, zz, col, row, keep_mask)

            # write to file
            img_name = self.img_names[i]
            P = list(P.reshape((1,)))
            affine_dict[img_name] = P

        # with open(os.path.join(self.tile_dir, 'affine_latlon.json'), 'w') as fp:
        #     json.dump(affine_dict, fp)

        return affine_dict

    def approx_perspective_utm(self):
        perspective_dict = {}

        aoi_ul_east = self.aoi_dict['x']
        aoi_ul_north = self.aoi_dict['y']

        for i in range(self.cnt):
            region_dict = self.region_dicts[i]
            ul_east = region_dict['x']
            ul_north = region_dict['y']
            lr_east = ul_east + region_dict['w']
            lr_north = ul_north - region_dict['h']
            zone_number = region_dict['zone_number']
            zone_letter = region_dict['zone_letter']

            # convert to lat, lon
            ul_lat, ul_lon = utm.to_latlon(ul_east, ul_north, zone_number, zone_letter)
            lr_lat, lr_lon = utm.to_latlon(lr_east, lr_north, zone_number, zone_letter)

            # create lat_lon_height grid
            lat_points = np.linspace(ul_lat, lr_lat, 20)
            lon_points = np.linspace(ul_lon, lr_lon, 20)
            z_points = np.linspace(self.min_height, self.max_height, 20)

            xx, yy, zz = gen_grid(lat_points, lon_points, z_points)
            col, row = self.rpc_models[i].projection(xx, yy, zz)

            # create north_east_height grid
            north_points = np.linspace(ul_north, lr_north, 20)
            east_points = np.linspace(ul_east, lr_east, 20)

            xx, yy, zz = gen_grid(north_points, east_points, z_points)

            # change to the common scene coordinate frame
            # use a smaller number and change to the right-handed coordinate frame
            xx = aoi_ul_north - xx
            yy = yy - aoi_ul_east

            # create keep_mask
            keep_mask = np.logical_and(col >=  0, row >= 0)
            keep_mask = np.logical_and(keep_mask, col < self.rpc_models[i].width)
            keep_mask = np.logical_and(keep_mask, row < self.rpc_models[i].height)

            K, R, t = solve_perspective(xx, yy, zz, col, row, keep_mask)

            quat = quaternion.from_rotation_matrix(R)
            # fx, fy, cx, cy, s, qvec, t
            params = [ K[0, 0], K[1, 1], K[0, 2], K[1, 2], K[0, 1],
                       quat.w, quat.x, quat.y, quat.z,
                       t[0, 0], t[1, 0], t[2, 0] ]

            img_name = self.img_names[i]
            perspective_dict[img_name] = params

        # with open(os.path.join(self.tile_dir, 'perspective_utm.json'), 'w') as fp:
        #     json.dump(perspective_dict, fp)

        return perspective_dict

