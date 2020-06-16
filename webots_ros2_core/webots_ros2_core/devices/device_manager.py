#!/usr/bin/env python

# Copyright 1996-2020 Cyberbotics Ltd.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Auto discover Webots devices and publish suitable ROS2 topics."""

import sys
from .camera_device import CameraDevice
from .led_device import LEDDevice
from .laser_device import LaserDevice
from .distance_sensor_device import DistanceSensorDevice
from .light_sensor_device import LightSensorDevice
from .robot_device import RobotDevice
from .imu_device import ImuDevice
from webots_ros2_core.utils import append_webots_python_lib_to_path
try:
    append_webots_python_lib_to_path()
    from controller import Node
except Exception as e:
    sys.stderr.write('"WEBOTS_HOME" is not correctly set.')
    raise e


class DeviceManager:
    """Discovers Webots devices and creates corresponding ROS2 topics/services."""

    def __init__(self, node, config=None):
        self.__node = node
        self.__devices = {}
        self.__config = config or {}
        self.__wb_devices = {}

        # Determine default global parameters
        self._auto = config.setdefault('@auto', True)

        # Disable `DeviceManager` if needed
        if not self._auto:
            return

        # Find devices
        self.__devices['@robot'] = RobotDevice(node, node.robot, self.__config.get('@robot', None))
        for i in range(node.robot.getNumberOfDevices()):
            wb_device = node.robot.getDeviceByIndex(i)
            device = None

            # Create ROS2 wrapped device
            if wb_device.getNodeType() == Node.CAMERA:
                device = CameraDevice(node, wb_device, self.__config.get(wb_device.getName(), None))
            elif wb_device.getNodeType() == Node.LED:
                device = LEDDevice(node, wb_device, self.__config.get(wb_device.getName(), None))
            elif wb_device.getNodeType() == Node.LIDAR:
                device = LaserDevice(node, wb_device, self.__config.get(wb_device.getName(), None))
            elif wb_device.getNodeType() == Node.DISTANCE_SENSOR:
                device = DistanceSensorDevice(node, wb_device, self.__config.get(wb_device.getName(), None))
            elif wb_device.getNodeType() == Node.LIGHT_SENSOR:
                device = LightSensorDevice(node, wb_device, self.__config.get(wb_device.getName(), None))

            # Add device to the list
            self.__wb_devices[wb_device.getName()] = wb_device
            if device:
                self.__devices[wb_device.getName()] = device

        # Multi-Webots-device (insert if not configured + create configured)
        self.__insert_imu_device()
        for config_key in self.__config.keys():
            if self.__is_imu_device(config_key):
                self.__devices[config_key] = ImuDevice(node, self.__get_imu_wb_devices_from_key(config_key))

        # Verify parameters
        for device_name in self.__config.keys():
            if device_name not in ['@auto'] and device_name not in self.__devices.keys():
                self.__node.get_logger().warn(
                    f'Device `{device_name}` is has not considered! The device doesn\'t exist or it is not supported.')

        # Create a loop
        self.__node.create_timer(1e-3 * int(node.robot.getBasicTimeStep()), self.__callback)

    def __callback(self):
        for device in self.__devices.values():
            device.step()

    def __is_imu_device(self, device_key):
        return any(self.__get_imu_wb_devices_from_key(device_key))

    def __get_imu_wb_devices_from_key(self, device_key):
        wb_device_names = device_key.split('|')

        accelerometer = None
        inertial_unit = None
        gyro = None

        for wb_device_name in wb_device_names:
            if wb_device_name in self.__wb_devices:
                if self.__wb_devices[wb_device_name] == Node.ACCELEROMETER:
                    accelerometer = self.__wb_devices[wb_device_name]
                elif self.__wb_devices[wb_device_name] == Node.INERTIAL_UNIT:
                    inertial_unit = self.__wb_devices[wb_device_name]
                elif self.__wb_devices[wb_device_name] == Node.GYRO:
                    gyro = self.__wb_devices[wb_device_name]

        return [accelerometer, inertial_unit, gyro]

    def __insert_imu_device(self):
        """Inserts Imu device only if non is configured and there is only one in the robot."""
        accelerometers = []
        inertial_units = []
        gyros = []

        # Ignore everything if any Imu is configured
        for config_key in self.__config.keys():
            if self.__is_imu_device(config_key):
                return

        # Classify and add to array
        for i in range(self.__node.robot.getNumberOfDevices()):
            wb_device = self.__node.robot.getDeviceByIndex(i)
            if wb_device.getNodeType() == Node.ACCELEROMETER:
                accelerometers.append(wb_device)
            elif wb_device.getNodeType() == Node.INERTIAL_UNIT:
                inertial_units.append(wb_device)
            elif wb_device.getNodeType() == Node.GYRO:
                gyros.append(wb_device)

        # If there is only one return the key
        if len(accelerometers) <= 1 and len(inertial_units) <= 1 and len(gyros) <= 1 and \
                (len(accelerometers) + len(inertial_units) + len(gyros)) > 0:
            imu_wb_devices = []
            if len(accelerometers) > 0:
                imu_wb_devices.append(accelerometers[0])
            if len(inertial_units) > 0:
                imu_wb_devices.append(inertial_units[0])
            if len(gyros) > 0:
                imu_wb_devices.append(gyros[0])
            device_key = '|'.join([wb_device.getName() for wb_device in imu_wb_devices])
            self.__devices[device_key] = ImuDevice(self.__node, imu_wb_devices, {
                'topic_name': '/imu',
                'frame_id': imu_wb_devices[0].getName()
            })
