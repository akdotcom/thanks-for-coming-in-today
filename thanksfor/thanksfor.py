from datetime import datetime, timedelta
import logging
import os

try: import simplejson as json
except ImportError: import json

from google.appengine.ext.webapp import template

from abstract_app import AbstractApp
from config import CONFIG
from thanksfor_model import User
from model import UserToken
import utils

class ThanksFor(AbstractApp):
  MOVING_AVG_WINDOW = 10
  EARLY_BIRD_DELTA = 30 * 60 # 30 minutes

  def appGet(self, client):
    data = { 'configured' : False }
    user_token = UserToken.get_from_cookie(self.request.cookies.get('session', None))
    if not (user_token and user_token.fs_id):
      self.redirect(utils.generateFoursquareAuthUri(client.oauth.client_id))
    if user_token and user_token.fs_id:
      request = User.all().filter('id =', user_token.fs_id)
      user = request.get()
      if user and user.office_id:
        data['configured'] = True
        client.set_access_token(user_token.token)
        venue_info = client.venues(user.office_id)
        data['venue_name'] = venue_info['venue']['name']
    logging.info('data %s' % data)
    path = os.path.join(os.path.dirname(__file__), 'settings.html')
    self.response.out.write(template.render(path, data))

  def appPost(self, client):
    reset = self.request.get('reset_office')
    logging.info("request %s" % self.request)
    user_token = UserToken.get_from_cookie(self.request.cookies.get('session', None))
    if user_token and user_token.fs_id and reset:
      request = User.all().filter('id =', user_token.fs_id)
      user = request.get()
      if user:
        logging.info('deleting the user!')
        user.delete()
    self.redirect(CONFIG['auth_success_uri_mobile'])

  def checkinTaskQueue(self, client, checkin_json):
    venue_id = checkin_json['venue']['id']
    request = User.all().filter('id =', checkin_json['user']['id'])
    user = request.get()
    if not user:
      # If they say "office" in their check-in, set this as their office
      if not 'shout' in checkin_json:
        logging.info("No shout, bailing")
        return
      shout = checkin_json['shout']
      if shout.lower().find('office') < 0:
        logging.info("Not at office, bailing")
        return
      user = User()
      user.id = checkin_json['user']['id']
      user.office_id = venue_id
      user.clockin_times = '[]'
      settings_url = CONFIG['prod_server'] + CONFIG['auth_success_uri_mobile']
      params = { 'text' : 'Ohh, so this is where you work. Duly noted!',
                 'url' : settings_url}
      client.checkins.reply(checkin_json['id'], params)

    if venue_id is not user.office_id:
      if venue_id is '4ef0e7cf7beb5932d5bdeb4e':
        #Easter egg!
        params = { 'text' : 'Foursquare HQ!? ' +
                  'I hear that place is full of sunshine and unicorns' }
        client.checkins.reply(checkin_json['id'], params)
      # They're not at the office
      return

    # What time is it?
    tz_offset = timedelta(minutes=checkin_json['timeZoneOffset'])
    date = datetime.utcfromtimestamp(checkin_json['createdAt']) + tz_offset
    time_of_day = self.calculateTimeOfDay(date)

    clockin_times = json.loads(user.clockin_times)
    avg_time = self.calculateAvg(clockin_times)
    diff = avg_time - time_of_day
    if diff > self.EARLY_BIRD_DELTA:
      if diff < 45:
        message = ('Look at you, clocking in %d minutes early today. Good job!'
                   % (diff / 60))
      elif diff < 115:
        message = 'Look at you, clocking in an hour early today. Good job!'
      else:
        message = ('Look at you, clocking in %d hours early today. Good job!'
                   % (diff / 60))
      params = { 'text' : message}
      client.checkins.reply(checkin_json['id'], params)

    # Update list of past clock-in times.    
    clockin_times.insert(0, time_of_day)
    if len(clockin_times) > self.MOVING_AVG_WINDOW:
      clockin_times.pop()
    user.clockin_times = json.dumps(clockin_times)
    user.put()

  def calculateTimeOfDay(self, dt):
    return (dt.hour * 60 + dt.minute) * 60 + dt.second

  def calculateAvg(self, numbers):
    if len(numbers) is 0:
      return 0
    avg = 0
    for num in numbers:
      avg += num
    return avg / len(numbers)
