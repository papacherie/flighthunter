import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))
import httpx
import app as fh


class FlightHunterTests(unittest.TestCase):
    def call(self, method, path, **kwargs):
        async def run():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=fh.app), base_url='http://test') as client:
                return await client.request(method, path, **kwargs)
        return asyncio.run(run())

    def test_home_and_health(self):
        self.assertEqual(self.call('GET','/').status_code, 200)
        self.assertIn('FlightHunter', self.call('GET','/').text)
        self.assertEqual(self.call('GET','/health').json()['ok'], True)

    def test_invalid_dates(self):
        r=self.call('POST','/api/search',json={'origin':'PAR','destination':'PVG','departure':'2027-08-20','return':'2027-07-29','adults':2,'children':1})
        self.assertEqual(r.status_code,400)

    def test_no_api_returns_no_fake_prices(self):
        with patch.object(fh, 'CLIENT',''), patch.object(fh, 'SECRET',''):
            r=self.call('POST','/api/search',json={'origin':'PAR','destination':'ALL','departure':'2027-07-29','return':'2027-08-20','adults':2,'children':1,'stops':'any'})
        self.assertEqual(r.status_code,200)
        d=r.json()
        self.assertEqual(d['offers'],[])
        self.assertEqual(d['status'],'not_configured')
        self.assertEqual(len(d['links']),2)
        self.assertIn('google.com',d['links'][0]['google'])

    def test_google_known_url_encoding(self):
        self.assertIn('GhoSCjIwMjctMDctMjlqBRIDUEFScgUSA1BWRxoaEgoyMDI3LTA4LTIwagUSA1BWR3IFEgNQQVJAAUABQAJIAZgBAQ',
            fh.flight_google_link('PAR','PVG','2027-07-29','2027-08-20',2,1))

    def test_offer_mapping_and_stops(self):
        data={'dictionaries':{'carriers':{'GF':'Gulf Air'}},'data':[
          {'id':'23','price':{'grandTotal':'2093.00','currency':'EUR'},
           'travelerPricings':[{'fareDetailsBySegment':[]},{'fareDetailsBySegment':[]},{'fareDetailsBySegment':[]}],
           'itineraries':[
             {'duration':'PT19H05M','segments':[
                {'carrierCode':'GF','departure':{'at':'2027-07-29T10:50','iataCode':'CDG'},'arrival':{'at':'2027-07-29T15:00','iataCode':'BAH'}},
                {'carrierCode':'GF','departure':{'at':'2027-07-29T18:00','iataCode':'BAH'},'arrival':{'at':'2027-07-30T11:55','iataCode':'PVG'}}]},
             {'duration':'PT20H05M','segments':[{'carrierCode':'GF','departure':{'at':'2027-08-20T17:00','iataCode':'PVG'},'arrival':{'at':'2027-08-21T11:00','iataCode':'CDG'}}]}]}]}
        offers=fh.normalize(data,'PVG','1',3)
        self.assertEqual(len(offers),1)
        self.assertEqual(offers[0]['carrier'],'Gulf Air')
        self.assertEqual(offers[0]['price'],2093)
        self.assertEqual(fh.normalize(data,'PVG','0',3),[])
        self.assertEqual(fh.normalize(data,'PVG','any',2),[])

    def test_api_code_required_with_keys(self):
        with patch.object(fh,'CLIENT','dummy'),patch.object(fh,'SECRET','dummy'),patch.object(fh,'CODE','private-code'):
            r=self.call('POST','/api/search',json={'origin':'PAR','destination':'PVG','departure':'2027-07-29','return':'2027-08-20','adults':2,'children':1,'stops':'any'})
            self.assertEqual(r.status_code,401)

if __name__=='__main__': unittest.main()
