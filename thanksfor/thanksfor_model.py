from google.appengine.ext import db

class User(db.Model):
  id = db.StringProperty()
  office_id = db.StringProperty()
  clockin_times = db.TextProperty()
  clockin_dts = db.TextProperty()
  best_dt = db.TextProperty()
