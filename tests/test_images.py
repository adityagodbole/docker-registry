# -*- coding: utf-8 -*-

import random

import base

from docker_registry.core import compat
import docker_registry.images as images
import docker_registry.lib.signals as signals

json = compat.json


class TestImages(base.TestCase):

    def test_simple(self):
        image_id = self.gen_random_string()
        parent_id = self.gen_random_string()
        layer_data = self.gen_random_string(1024)
        self.upload_image(parent_id, parent_id=None, layer=layer_data)

        self.upload_image(image_id, parent_id=parent_id, layer=layer_data)
        # test fetching the ancestry
        resp = self.http_client.get('/v1/images/{0}/ancestry'.format(image_id))
        # Note(dmp): unicode patch XXX not applied assume requests does the job
        ancestry = json.loads(resp.data)
        self.assertEqual(len(ancestry), 2)
        self.assertEqual(ancestry[0], image_id)
        self.assertEqual(ancestry[1], parent_id)

    def test_notfound(self):
        resp = self.http_client.get('/v1/images/{0}/json'.format(
            self.gen_random_string()))
        self.assertEqual(resp.status_code, 404, resp.data)
