"""
This was created to track my home IP on my private domain.
I chose to use cloudflare free DNS service to have API access to update my DNS records.
This will run periodically from my home server and use multiple IP identification services.

https://dash.cloudflare.com/profile/api-tokens
"""
import argparse
import logging
import os
import random

import requests
import dotenv

dotenv.load_dotenv()

CLOUDFLARE_API_TOKEN = os.environ.get('CLOUDFLARE_API_TOKEN')
ZONE_ID = os.environ.get('ZONE_ID')
DOMAIN = os.environ.get('DOMAIN')
A_RECORD_NAME = os.environ.get('A_RECORD_NAME')
FQDN = f'{A_RECORD_NAME}.{DOMAIN}'

LOG = logging.getLogger('krets')
LOG.addHandler(logging.StreamHandler())
LOG.handlers[-1].setFormatter(logging.Formatter('%(levelname)s: %(message)s'))

class Cloudflare:
    def __init__(self, zone_id=ZONE_ID):
        self.base_url = 'https://api.cloudflare.com/client/v4'
        self.session = requests.Session()
        self.session.headers = {
            'Authorization': f'Bearer {CLOUDFLARE_API_TOKEN}',
            'Content-Type': 'application/json'
        }
        self.zone_id = zone_id

    def _request(self, method, endpoint, **kwargs):
        url = f"{self.base_url}/{endpoint}"
        LOG.debug(f"{method}: {url} params: {kwargs.get('params', {})}")
        response = self.session.request(method, url, **kwargs)
        LOG.debug(f"response: {response.status_code} {response.reason}")
        response.raise_for_status()
        return response.json()

    def get(self, endpoint, **kwargs):
        return self._request('GET', endpoint, **kwargs)

    def put(self, endpoint, **kwargs):
        return self._request('PUT', endpoint, **kwargs)

    def dns_records(self, type='A', name=None):
        params = {'type': type}
        if name:
            params['name'] = name
        return self.get(f'zones/{self.zone_id}/dns_records', params=params).get('result')

    def record_by_name(self, name):
        record_names = {_.get('name'):_ for _ in self.dns_records()}
        return record_names.get(FQDN)

    def update_dns_record(self, record_id, ip_address):
        data = {
            'type': 'A',
            'name': A_RECORD_NAME,
            'content': ip_address,
            'ttl': 1,
            'proxied': False
        }
        return self.put(f'zones/{self.zone_id}/dns_records/{record_id}', json=data)


def get_current_ip():
    services = [
        'https://api.ipify.org?format=json',
        'https://api.myip.com',
        'https://ipinfo.io/ip',
        'https://checkip.amazonaws.com',
        'https://ident.me'
    ]
    random.shuffle(services)
    for service in services:
        try:
            response = requests.get(service)
            response.raise_for_status()
            try:
                data = response.json()
                value = data.get('ip', None)
            except ValueError:
                value = response.text.strip()
            LOG.debug(f"Found current IP: {value} from: {service}")
            return value

        except requests.RequestException as error:
            LOG.warning(f"Failed to get IP from {service}: {error}")
            continue
    return None

def parse_args():
    parser = argparse.ArgumentParser('Cloudflare DNS Updater')
    parser.add_argument('-v', '--verbose', action='store_true')
    return parser.parse_args()

def main():

    args = parse_args()
    level = logging.DEBUG if args.verbose else logging.INFO
    LOG.setLevel(level)

    cloudflare = Cloudflare()
    record = cloudflare.record_by_name(FQDN)

    if record:
        record_id = record.get('id')
        record_ip = record.get('content')
        current_ip = get_current_ip()
        if record_ip == current_ip:
            LOG.info(f"Current IP: {current_ip} matches '{FQDN}'")
        elif cloudflare.update_dns_record(record_id, current_ip):
            LOG.info(f"Successfully updated '{FQDN}' record to {current_ip}")
        else:
            # raise for status will likely bypass this branch
            LOG.error(f"Failed to update DNS record for '{FQDN}'")
    else:
        LOG.warning(f"No A record found for '{FQDN}'")
    pass


if __name__ == '__main__':
    main()