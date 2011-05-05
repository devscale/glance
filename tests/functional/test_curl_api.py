# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2011 OpenStack, LLC
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

"""Functional test case that utilizes cURL against the API server"""

import json
import os
import tempfile
import unittest

from tests import functional
from tests.utils import execute

FIVE_KB = 5 * 1024
FIVE_GB = 5 * 1024 * 1024 * 1024


class TestCurlApi(functional.FunctionalTest):

    """Functional tests using straight cURL against the API server"""

    def test_get_head_simple_post(self):
        """
        We test the following sequential series of actions:

        0. GET /images
        - Verify no public images
        1. GET /images/detail
        - Verify no public images
        2. HEAD /images/1
        - Verify 404 returned
        3. POST /images with public image named Image1 with a location
        attribute and no custom properties
        - Verify 201 returned
        4. HEAD /images/1
        - Verify HTTP headers have correct information we just added
        5. GET /images/1
        - Verify all information on image we just added is correct
        6. GET /images
        - Verify the image we just added is returned
        7. GET /images/detail
        - Verify the image we just added is returned
        8. PUT /images/1 with custom properties of "distro" and "arch"
        - Verify 200 returned
        9. GET /images/1
        - Verify updated information about image was stored
        10. PUT /images/1
        - Remove a previously existing property.
        11. PUT /images/1
        - Add a previously deleted property.
        """

        self.cleanup()
        api_port, reg_port, conf_file = self.start_servers()

        # 0. GET /images
        # Verify no public images
        cmd = "curl -g http://0.0.0.0:%d/images" % api_port

        exitcode, out, err = execute(cmd)

        self.assertEqual(0, exitcode)
        self.assertEqual('{"images": []}', out.strip())

        # 1. GET /images/detail
        # Verify no public images
        cmd = "curl -g http://0.0.0.0:%d/images/detail" % api_port

        exitcode, out, err = execute(cmd)

        self.assertEqual(0, exitcode)
        self.assertEqual('{"images": []}', out.strip())

        # 2. HEAD /images/1
        # Verify 404 returned
        cmd = "curl -i -X HEAD http://0.0.0.0:%d/images/1" % api_port

        exitcode, out, err = execute(cmd)

        self.assertEqual(0, exitcode)

        lines = out.split("\r\n")
        status_line = lines[0]

        self.assertEqual("HTTP/1.1 404 Not Found", status_line)

        # 3. POST /images with public image named Image1
        # attribute and no custom properties. Verify a 200 OK is returned
        image_data = "*" * FIVE_KB

        cmd = ("curl -i -X POST "
               "-H 'Expect: ' "  # Necessary otherwise sends 100 Continue
               "-H 'Content-Type: application/octet-stream' "
               "-H 'X-Image-Meta-Name: Image1' "
               "-H 'X-Image-Meta-Is-Public: True' "
               "--data-binary \"%s\" "
               "http://0.0.0.0:%d/images") % (image_data, api_port)

        exitcode, out, err = execute(cmd)
        self.assertEqual(0, exitcode)

        lines = out.split("\r\n")
        status_line = lines[0]

        self.assertEqual("HTTP/1.1 201 Created", status_line)

        # 4. HEAD /images
        # Verify image found now
        cmd = "curl -i -X HEAD http://0.0.0.0:%d/images/1" % api_port

        exitcode, out, err = execute(cmd)

        self.assertEqual(0, exitcode)

        lines = out.split("\r\n")
        status_line = lines[0]

        self.assertEqual("HTTP/1.1 200 OK", status_line)
        self.assertTrue("X-Image-Meta-Name: Image1" in out)

        # 5. GET /images/1
        # Verify all information on image we just added is correct

        cmd = "curl -i -g http://0.0.0.0:%d/images/1" % api_port

        exitcode, out, err = execute(cmd)

        self.assertEqual(0, exitcode)

        lines = out.split("\r\n")

        self.assertEqual("HTTP/1.1 200 OK", lines.pop(0))

        # Handle the headers
        image_headers = {}
        std_headers = {}
        other_lines = []
        for line in lines:
            if line.strip() == '':
                continue
            if line.startswith("X-Image"):
                pieces = line.split(":")
                key = pieces[0].strip()
                value = ":".join(pieces[1:]).strip()
                image_headers[key] = value
            elif ':' in line:
                pieces = line.split(":")
                key = pieces[0].strip()
                value = ":".join(pieces[1:]).strip()
                std_headers[key] = value
            else:
                other_lines.append(line)

        expected_image_headers = {
            'X-Image-Meta-Id': '1',
            'X-Image-Meta-Name': 'Image1',
            'X-Image-Meta-Is_public': 'True',
            'X-Image-Meta-Status': 'active',
            'X-Image-Meta-Disk_format': '',
            'X-Image-Meta-Container_format': '',
            'X-Image-Meta-Size': str(FIVE_KB),
            'X-Image-Meta-Location': 'file://%s/1' % self.image_dir}

        expected_std_headers = {
            'Content-Length': str(FIVE_KB),
            'Content-Type': 'application/octet-stream'}

        for expected_key, expected_value in expected_image_headers.items():
            self.assertTrue(expected_key in image_headers,
                            "Failed to find key %s in image_headers"
                            % expected_key)
            self.assertEqual(expected_value, image_headers[expected_key],
                            "For key '%s' expected header value '%s'. Got '%s'"
                            % (expected_key,
                               expected_value,
                               image_headers[expected_key]))

        for expected_key, expected_value in expected_std_headers.items():
            self.assertTrue(expected_key in std_headers,
                            "Failed to find key %s in std_headers"
                            % expected_key)
            self.assertEqual(expected_value, std_headers[expected_key],
                            "For key '%s' expected header value '%s'. Got '%s'"
                            % (expected_key,
                               expected_value,
                               std_headers[expected_key]))

        # Now the image data...
        expected_image_data = "*" * FIVE_KB

        # Should only be a single "line" left, and
        # that's the image data
        self.assertEqual(1, len(other_lines))
        self.assertEqual(expected_image_data, other_lines[0])

        # 6. GET /images
        # Verify no public images
        cmd = "curl -g http://0.0.0.0:%d/images" % api_port

        exitcode, out, err = execute(cmd)

        self.assertEqual(0, exitcode)

        expected_result = {"images": [
            {"container_format": None,
             "disk_format": None,
             "id": 1,
             "name": "Image1",
             "checksum": "c2e5db72bd7fd153f53ede5da5a06de3",
             "size": 5120}]}
        self.assertEqual(expected_result, json.loads(out.strip()))

        # 7. GET /images/detail
        # Verify image and all its metadata
        cmd = "curl -g http://0.0.0.0:%d/images/detail" % api_port

        exitcode, out, err = execute(cmd)

        self.assertEqual(0, exitcode)

        expected_image = {
            "status": "active",
            "name": "Image1",
            "deleted": False,
            "container_format": None,
            "disk_format": None,
            "id": 1,
            "location": "file://%s/1" % self.image_dir,
            "is_public": True,
            "deleted_at": None,
            "properties": {},
            "size": 5120}

        image = json.loads(out.strip())['images'][0]

        for expected_key, expected_value in expected_image.items():
            self.assertTrue(expected_key in image,
                            "Failed to find key %s in image"
                            % expected_key)
            self.assertEqual(expected_value, expected_image[expected_key],
                            "For key '%s' expected header value '%s'. Got '%s'"
                            % (expected_key,
                               expected_value,
                               image[expected_key]))

        # 8. PUT /images/1 with custom properties of "distro" and "arch"
        # Verify 200 returned

        cmd = ("curl -i -X PUT "
               "-H 'X-Image-Meta-Property-Distro: Ubuntu' "
               "-H 'X-Image-Meta-Property-Arch: x86_64' "
               "http://0.0.0.0:%d/images/1") % api_port

        exitcode, out, err = execute(cmd)
        self.assertEqual(0, exitcode)

        lines = out.split("\r\n")
        status_line = lines[0]

        self.assertEqual("HTTP/1.1 200 OK", status_line)

        # 9. GET /images/detail
        # Verify image and all its metadata
        cmd = "curl -g http://0.0.0.0:%d/images/detail" % api_port

        exitcode, out, err = execute(cmd)

        self.assertEqual(0, exitcode)

        expected_image = {
            "status": "active",
            "name": "Image1",
            "deleted": False,
            "container_format": None,
            "disk_format": None,
            "id": 1,
            "location": "file://%s/1" % self.image_dir,
            "is_public": True,
            "deleted_at": None,
            "properties": {'distro': 'Ubuntu', 'arch': 'x86_64'},
            "size": 5120}

        image = json.loads(out.strip())['images'][0]

        for expected_key, expected_value in expected_image.items():
            self.assertTrue(expected_key in image,
                            "Failed to find key %s in image"
                            % expected_key)
            self.assertEqual(expected_value, image[expected_key],
                            "For key '%s' expected header value '%s'. Got '%s'"
                            % (expected_key,
                               expected_value,
                               image[expected_key]))

        # 10. PUT /images/1 and remove a previously existing property.
        cmd = ("curl -i -X PUT "
               "-H 'X-Image-Meta-Property-Arch: x86_64' "
               "http://0.0.0.0:%d/images/1") % api_port

        exitcode, out, err = execute(cmd)
        self.assertEqual(0, exitcode)

        lines = out.split("\r\n")
        status_line = lines[0]

        self.assertEqual("HTTP/1.1 200 OK", status_line)

        cmd = "curl -g http://0.0.0.0:%d/images/detail" % api_port

        exitcode, out, err = execute(cmd)

        self.assertEqual(0, exitcode)

        image = json.loads(out.strip())['images'][0]
        self.assertEqual(1, len(image['properties']))
        self.assertEqual('x86_64', image['properties']['arch'])

        # 11. PUT /images/1 and add a previously deleted property.
        cmd = ("curl -i -X PUT "
               "-H 'X-Image-Meta-Property-Distro: Ubuntu' "
               "-H 'X-Image-Meta-Property-Arch: x86_64' "
               "http://0.0.0.0:%d/images/1") % api_port

        exitcode, out, err = execute(cmd)
        self.assertEqual(0, exitcode)

        lines = out.split("\r\n")
        status_line = lines[0]

        self.assertEqual("HTTP/1.1 200 OK", status_line)

        cmd = "curl -g http://0.0.0.0:%d/images/detail" % api_port

        exitcode, out, err = execute(cmd)

        self.assertEqual(0, exitcode)

        image = json.loads(out.strip())['images'][0]
        self.assertEqual(2, len(image['properties']))
        self.assertEqual('x86_64', image['properties']['arch'])
        self.assertEqual('Ubuntu', image['properties']['distro'])

        self.stop_servers()

    def test_queued_process_flow(self):
        """
        We test the process flow where a user registers an image
        with Glance but does not immediately upload an image file.
        Later, the user uploads an image file using a PUT operation.
        We track the changing of image status throughout this process.

        0. GET /images
        - Verify no public images
        1. POST /images with public image named Image1 with no location
           attribute and no image data.
        - Verify 201 returned
        2. GET /images
        - Verify one public image
        3. HEAD /images/1
        - Verify image now in queued status
        4. PUT /images/1 with image data
        - Verify 200 returned
        5. HEAD /images/1
        - Verify image now in active status
        6. GET /images
        - Verify one public image
        """

        self.cleanup()
        api_port, reg_port, conf_file = self.start_servers()

        # 0. GET /images
        # Verify no public images
        cmd = "curl -g http://0.0.0.0:%d/images" % api_port

        exitcode, out, err = execute(cmd)

        self.assertEqual(0, exitcode)
        self.assertEqual('{"images": []}', out.strip())

        # 1. POST /images with public image named Image1
        # with no location or image data

        cmd = ("curl -i -X POST "
               "-H 'Expect: ' "  # Necessary otherwise sends 100 Continue
               "-H 'X-Image-Meta-Name: Image1' "
               "-H 'X-Image-Meta-Is-Public: True' "
               "http://0.0.0.0:%d/images") % api_port

        exitcode, out, err = execute(cmd)
        self.assertEqual(0, exitcode)

        lines = out.split("\r\n")
        status_line = lines[0]

        self.assertEqual("HTTP/1.1 201 Created", status_line)

        # 2. GET /images
        # Verify 1 public image
        cmd = "curl -g http://0.0.0.0:%d/images" % api_port

        exitcode, out, err = execute(cmd)

        self.assertEqual(0, exitcode)
        image = json.loads(out.strip())['images'][0]
        expected = {"name": "Image1",
                    "container_format": None,
                    "disk_format": None,
                    "checksum": None,
                    "id": 1,
                    "size": 0}
        self.assertEqual(expected, image)

        # 3. HEAD /images
        # Verify status is in queued
        cmd = "curl -i -X HEAD http://0.0.0.0:%d/images/1" % api_port

        exitcode, out, err = execute(cmd)

        self.assertEqual(0, exitcode)

        lines = out.split("\r\n")
        status_line = lines[0]

        self.assertEqual("HTTP/1.1 200 OK", status_line)
        self.assertTrue("X-Image-Meta-Name: Image1" in out)
        self.assertTrue("X-Image-Meta-Status: queued" in out)

        # 4. PUT /images/1 with image data, verify 200 returned
        image_data = "*" * FIVE_KB

        cmd = ("curl -i -X PUT "
               "-H 'Expect: ' "  # Necessary otherwise sends 100 Continue
               "-H 'Content-Type: application/octet-stream' "
               "--data-binary \"%s\" "
               "http://0.0.0.0:%d/images/1") % (image_data, api_port)

        exitcode, out, err = execute(cmd)
        self.assertEqual(0, exitcode)

        lines = out.split("\r\n")
        status_line = lines[0]

        self.assertEqual("HTTP/1.1 200 OK", status_line)

        # 5. HEAD /images
        # Verify status is in active
        cmd = "curl -i -X HEAD http://0.0.0.0:%d/images/1" % api_port

        exitcode, out, err = execute(cmd)

        self.assertEqual(0, exitcode)

        lines = out.split("\r\n")
        status_line = lines[0]

        self.assertEqual("HTTP/1.1 200 OK", status_line)
        self.assertTrue("X-Image-Meta-Name: Image1" in out)
        self.assertTrue("X-Image-Meta-Status: active" in out)

        # 6. GET /images
        # Verify 1 public image still...
        cmd = "curl -g http://0.0.0.0:%d/images" % api_port

        exitcode, out, err = execute(cmd)

        self.assertEqual(0, exitcode)
        image = json.loads(out.strip())['images'][0]
        expected = {"name": "Image1",
                    "container_format": None,
                    "disk_format": None,
                    "checksum": 'c2e5db72bd7fd153f53ede5da5a06de3',
                    "id": 1,
                    "size": 5120}
        self.assertEqual(expected, image)

    def test_size_greater_2G_mysql(self):
        """
        A test against the actual datastore backend for the registry
        to ensure that the image size property is not truncated.

        :see https://bugs.launchpad.net/glance/+bug/739433
        """

        self.cleanup()
        api_port, reg_port, conf_file = self.start_servers()

        # 1. POST /images with public image named Image1
        # attribute and a size of 5G. Use the HTTP engine with an
        # X-Image-Meta-Location attribute to make Glance forego
        # "adding" the image data.
        # Verify a 200 OK is returned
        cmd = ("curl -i -X POST "
               "-H 'Expect: ' "  # Necessary otherwise sends 100 Continue
               "-H 'X-Image-Meta-Location: http://example.com/fakeimage' "
               "-H 'X-Image-Meta-Size: %d' "
               "-H 'X-Image-Meta-Name: Image1' "
               "-H 'X-Image-Meta-Is-Public: True' "
               "http://0.0.0.0:%d/images") % (FIVE_GB, api_port)

        exitcode, out, err = execute(cmd)
        self.assertEqual(0, exitcode)

        lines = out.split("\r\n")
        status_line = lines[0]

        self.assertEqual("HTTP/1.1 201 Created", status_line)

        # Get the ID of the just-added image. This may NOT be 1, since the
        # database in the environ variable TEST_GLANCE_CONNECTION may not
        # have been cleared between test cases... :(
        new_image_uri = None
        for line in lines:
            if line.startswith('Location:'):
                new_image_uri = line[line.find(':') + 1:].strip()

        self.assertTrue(new_image_uri is not None,
                        "Could not find a new image URI!")

        # 2. HEAD /images
        # Verify image size is what was passed in, and not truncated
        cmd = "curl -i -X HEAD %s" % new_image_uri

        exitcode, out, err = execute(cmd)

        self.assertEqual(0, exitcode)

        lines = out.split("\r\n")
        status_line = lines[0]

        self.assertEqual("HTTP/1.1 200 OK", status_line)
        self.assertTrue("X-Image-Meta-Size: %d" % FIVE_GB in out,
                        "Size was supposed to be %d. Got:\n%s."
                        % (FIVE_GB, out))

        self.stop_servers()

    def test_traceback_not_consumed(self):
        """
        A test that errors coming from the POST API do not
        get consumed and print the actual error message, and
        not something like &lt;traceback object at 0x1918d40&gt;

        :see https://bugs.launchpad.net/glance/+bug/755912
        """

        self.cleanup()
        api_port, reg_port, conf_file = self.start_servers()

        # POST /images with binary data, but not setting
        # Content-Type to application/octet-stream, verify a
        # 400 returned and that the error is readable.
        with tempfile.NamedTemporaryFile() as test_data_file:
            test_data_file.write("XXX")
            test_data_file.flush()
            cmd = ("curl -i -X POST --upload-file %s "
                   "http://0.0.0.0:%d/images") % (test_data_file.name,
                                                  api_port)

            exitcode, out, err = execute(cmd)
            self.assertEqual(0, exitcode)

            lines = out.split("\r\n")
            status_line = lines.pop(0)

            self.assertEqual("HTTP/1.1 400 Bad Request", status_line)
            expected = "Content-Type must be application/octet-stream"
            self.assertTrue(expected in out,
                            "Could not find '%s' in '%s'" % (expected, out))

        self.stop_servers()
