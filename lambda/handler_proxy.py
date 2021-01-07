import json
import os
from botocore.vendored import requests


def handler(event, context):
    print('request: {}'.format(json.dumps(event)))
    host = os.environ['apihost']
    print('host: %s' % (host))
    requesthost = 'https://'+host+'/prod' + event['path']
    print('requesting: %s' % requesthost)
    response = requests.get(requesthost)
    print('response: %s %s' % (response.status_code, response.text))
    return {
        'statusCode': response.status_code,
        'headers': dict(response.headers),
        'body': response.text
    }