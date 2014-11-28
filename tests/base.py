# -*- coding: utf-8 -*-

import hashlib
import os
import random
import string
import unittest
import httplib2
import re
import json

from docker_registry.core import compat
import docker_registry.wsgi as wsgi

data_dir = os.path.join(os.path.dirname(__file__), "data")

class DummyResp:
    def __init__(self, headers, data):
        self.headers = headers
        self.status_code = headers.status
        self.data = data

class RealHttpClient:
    def __init__(self, base_url):
        self.conn = httplib2.Http()
        self.baseurl = "http://" + base_url

    def make_resp(self, r):
        return DummyResp(r[0], r[1])

    def full_url(self, url):
        return self.baseurl + url

    def prep_headers(self, headers):
        if not headers.get('User-Agent'):
            headers['User-Agent'] = ('docker/0.10.0 go/go1.2.1 git-commit/3600720 '
                                    'kernel/3.8.0-19-generic os/linux arch/amd64')

    def put(self, url, data = None, headers = {}, input_stream = None):
        self.prep_headers(headers)
        if input_stream:
            data = input_stream.read()
        return self.make_resp(self.conn.request(self.full_url(url), "PUT", data, headers))

    def get(self, url, headers = {}):
        self.prep_headers(headers)
        return self.make_resp(self.conn.request(self.full_url(url), "GET", None, headers))

    def delete(self, url, headers = {}):
        self.prep_headers(headers)
        return self.make_resp(self.conn.request(self.full_url(url), "DELETE", None, headers))

class TestCase(unittest.TestCase):

    def __init__(self, *args, **kwargs):
        unittest.TestCase.__init__(self, *args, **kwargs)
        wsgi.app.testing = True
        self.http_client = RealHttpClient("localhost:5000")

    def gen_random_string(self, length=16):
        return ''.join([random.choice(string.ascii_uppercase + string.digits)
                        for x in range(length)]).lower()

    def set_image_checksum(self, image_id, checksum):
        headers = {'X-Docker-Checksum-Payload': checksum}
        url = '/v1/images/{0}/checksum'.format(image_id)
        resp = self.http_client.put(url, headers=headers)
        self.assertEqual(resp.status_code, 200, resp.data)
        # Once the checksum test passed, the image is "locked"
        resp = self.http_client.put(url, headers=headers)
        self.assertEqual(resp.status_code, 409, resp.data)
        # Cannot set the checksum on an non-existing image
        url = '/v1/images/{0}/checksum'.format(self.gen_random_string())
        resp = self.http_client.put(url, headers=headers)
        self.assertEqual(resp.status_code, 404, resp.data)

    def upload_image(self, image_id, parent_id, layer):
        json_obj = {
            'id': image_id
        }
        if parent_id:
            json_obj['parent'] = parent_id
        json_data = compat.json.dumps(json_obj)
        h = hashlib.sha256(json_data)
        h.update(layer)
        layer_checksum = 'sha256:{0}'.format(h.hexdigest())
        headers = {'X-Docker-Checksum-Payload': layer_checksum}
        resp = self.http_client.put('/v1/images/{0}/json'.format(image_id),
                                    headers=headers, data=json_data)
        self.assertEqual(resp.status_code, 200, resp.data)
        # Make sure I cannot download the image before push is complete
        resp = self.http_client.get('/v1/images/{0}/json'.format(image_id))
        self.assertEqual(resp.status_code, 400, resp.data)
        layer_file = compat.StringIO(layer)
        resp = self.http_client.put('/v1/images/{0}/layer'.format(image_id),
                                    input_stream=layer_file)
        layer_file.close()
        self.assertEqual(resp.status_code, 200, resp.data)
        self.set_image_checksum(image_id, layer_checksum)
        # Push done, test reading the image
        resp = self.http_client.get('/v1/images/{0}/json'.format(image_id))
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(resp.headers.get('x-docker-size'), str(len(layer)))
        checksums = resp.headers['x-docker-checksum-payload']
        checksums = checksums.split(', ')
        self.assertEqual(checksums[0], layer_checksum)