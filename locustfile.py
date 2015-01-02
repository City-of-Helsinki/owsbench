import random
import math
from locust import HttpLocust, TaskSet, task
from lxml import etree


class WMSLayer(object):
    def __init__(self, xml_el):
        #print(etree.tostring(xml_el))
        self.name = xml_el.find('Name').text
        self.bbox = dict(xml_el.find('BoundingBox').attrib.items())
        for n in ['minx', 'maxx', 'maxy', 'miny']:
            self.bbox[n] = float(self.bbox[n])
        self.width = self.bbox['maxx'] - self.bbox['minx']
        self.height = self.bbox['maxy'] - self.bbox['miny']


class WMSTaskSet(TaskSet):
    default_params = {
        'service': 'wms',
        'version': '1.1.1',
    }

    def on_start(self):
        url_params = self.default_params.copy()
        url_params.update({
            'request': 'GetCapabilities'
        })
        resp = self.client.get("/wms", params=url_params, catch_response=True)
        content_type = resp.headers['content-type']
        assert content_type == 'application/vnd.ogc.wms_xml'

        root = etree.fromstring(resp.content)
        layers = root.xpath('//Capability/Layer/Layer')
        assert len(layers) > 0

        self.layers = [WMSLayer(el) for el in layers]
        #for l in self.layers:
        #    print l.name

    @task
    def get_map(self, layer=None):
        if not layer:
            possible_layers = ['hel:Karttasarja']
            layers = [l for l in self.layers if l.name in possible_layers]
            layer = random.choice(layers)

        dim = 256
        img_fmt = 'image/jpeg'

        url_params = self.default_params.copy()
        url_params.update({
            'request': 'GetMap',
            'layers': layer.name,
            'styles': '',
            'srs': layer.bbox['SRS'],
            'width': dim,
            'height': dim,
            'format': img_fmt,
        })

        # min spatial resolution 5cm
        min_res = 0.05
        max_res = min(layer.height, layer.width) / dim
        max_exp = math.log(max_res / min_res, 2)
        exp = random.randint(0, int(max_exp))
        res = min_res * 2**exp

        minx = random.uniform(layer.bbox['minx'], layer.bbox['maxx'] - res * dim)
        miny = random.uniform(layer.bbox['miny'], layer.bbox['maxy'] - res * dim)
        #max_res = min(layer.bbox['maxx'] - minx, layer.bbox['maxy'] - miny)
        #max_res /= dim

        maxx = minx + res * dim
        maxy = miny + res * dim
        bbox = [str(f) for f in [minx, miny, maxx, maxy]]
        url_params['bbox'] = ','.join(bbox)

        name = 'WMS-GetMap-%s' % layer.name
        name += '-%6sm' % ('%.2f' % res)
        args = dict(params=url_params, name=name, catch_response=True)
        with self.client.get("/wms", **args) as resp:
            #print(resp.request.url)

            if resp.status_code != 200:
                print("status %d" % resp.status_code)
                print(resp.request.url)
                return
            if resp.headers['content-type'] != img_fmt:
                resp.failure('Invalid content type')
                print("content type: %s" % resp.headers['content-type'])
                print(resp.request.url)
                print(resp.content)
                return
            f = open('/tmp/locust/%s.png' % name, 'w')
            f.write(resp.content)
            f.close()


class WMSBench(HttpLocust):
    task_set = WMSTaskSet
    host = "http://geoserver.hel.fi/geoserver"

    # we assume someone who is browsing the Locust docs,
    # generally has a quite long waiting time (between
    # 20 and 600 seconds), since there's a bunch of text
    # on each page
    min_wait = 0
    #max_wait = 600 * 1000
