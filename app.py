from flask_sqlalchemy import SQLAlchemy
import requests as r
import smtplib
from twilio.rest import Client
from datetime import datetime
import pytz
import json
import atexit
from flask import request
import sys
import configparser
from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask,render_template

app = Flask(__name__)

config = configparser.RawConfigParser(interpolation=None)
config.read('ConfigFile.properties')
from_email_id = config.get('Credentials', 'from.email.id')
from_email_password = config.get('Credentials', 'from.email.password')
from_phone = config.get('Credentials', 'from.phone')
account_sid = config.get('Credentials', 'twilio.account.sid')
auth_token = config.get('Credentials', 'twilio.auth.token')


app.config['SQLALCHEMY_DATABASE_URI'] = config.get('Database', 'sqlalchemy.database.uri')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = (config.get('Database', 'sqlalchemy.database.uri')=="True")
app.config['DEBUG'] = (config.get('Generic', 'debug')=="True")

db = SQLAlchemy(app)

class Requests(db.Model):
    __tablename__ = 'requests'
    id = db.Column(db.Integer, primary_key=True)
    mail_id = db.Column(db.String(200))
    mobile_number = db.Column(db.String(20))
    district_code = db.Column(db.String(20))
    vaccine_type = db.Column(db.String(100))
    age = db.Column(db.String(100))
    dose = db.Column(db.String(100))

    def __init__(self, mail_id, mobile_number, district_code, vaccine_type, age, dose):
        self.mail_id = mail_id
        self.mobile_number= mobile_number
        self.district_code = district_code
        self.vaccine_type = vaccine_type
        self.age = age
        self.dose = dose


@app.route("/")                   # at the end point /
def hello():
    print("hello")
    sys.stdout.flush()
    return render_template('index.html')
    #return app.send_static_file('index.html')        # which returns "hello world"

@app.route('/addDetails/', methods=['POST'])
def insertData():
    data = request.form
    mailId = data["mailId"]
    districtCode = data["districtCode"]
    age = data["age"]
    mobileNumber = data["mobileNumber"]
    vaccineType = data["vaccineType"]
    dose = data["dose"]

    if not mailId:
        return "Email address is missing"
    elif not districtCode:
        return "District is not selected"
    else:
        # details = mailId+":"+districtCode+":"+mobileNumber+":"+age+":"+vaccineType+":"+dose
        # hs = open("data.txt", "a")
        # hs.write(details + "\n")

        data = Requests(mailId, mobileNumber, districtCode, vaccineType, age, dose)
        db.session.add(data)
        db.session.commit()

        return "Data added successfully"

@app.route('/removeDetails/', methods=['POST'])
def removeData():
    data = request.form
    mailId=data["mailId"]

    reqs = Requests.query.filter_by(mail_id=mailId).all()
    for i in reqs:
        db.session.delete(i)
        db.session.commit()

    return "deleted"

def getReqId():
    pass

def sendEmail(avaialbleSlots, mailId):
    s = smtplib.SMTP('smtp.gmail.com', 587)
    s.ehlo()
    s.starttls()
    s.login(from_email_id, from_email_password)
    Subject = "Availablity of Covid Vaccine slots"
    Text = ''.join(str(e) for e in avaialbleSlots)
    message = 'Subject: {}\n\n{}'.format(Subject, Text)
    s.sendmail(from_email_id, mailId, message)
    s.quit()
    print("Mail sent!")
    sys.stdout.flush()


def sendText(avaialbleSlots, mobileNumber):
    if mobileNumber is not None or mobileNumber!="":
        client = Client(account_sid, auth_token)
        Text = ''.join(str(e) for e in avaialbleSlots)
        Text = Text[:1500]

        message = client.messages.create(from_= from_phone,
                                         to= str(mobileNumber),
                                         body=Text)

        print(message)
        print("SMS sent!")
        # sys.stdout.flush()


def checkDetails(rawData,age,vaccineType, dose):
    jsonData = json.loads(rawData)
    slots = []
    availableSlots = []
    availableSlotsShort = []

    if age=="45+":
        min_age_limit = 45
        max_age_limit = 1000
    elif age=="18-45":
        min_age_limit = 18
        max_age_limit = 44
    else:
        min_age_limit = 0
        max_age_limit = 1000

    print(dose)
    if dose=="dose1":
        dose="available_capacity_dose1"
    elif dose=="dose2":
        dose="available_capacity_dose2"
    else:
        dose="available_capacity"


    # check if there are any centers
    for center in jsonData["centers"]:
        # check for each session in a center which has further details regarding availability, age, dose
        for session in center["sessions"]:
            if int(session[dose]) > 0 and int(session['min_age_limit']) >= min_age_limit and int(session['min_age_limit']) <= max_age_limit:
                if vaccineType == "any":
                    messageContent = str(session['available_capacity']) + " slots available on " + str(
                        session["date"]) + " at " + str(center["name"]) + ", " + str(center["address"]) + ", " + str(
                        center["district_name"]) + ", " + str(center["state_name"] + "\n\n")
                    messageContentShort = "slotsAvailable-" + str(session["date"]) + "," + str(
                        center["state_name"] + "\n")
                    availableSlots.append(messageContent)
                    availableSlotsShort.append(messageContentShort)

                elif vaccineType == session['vaccine']:
                    messageContent = str(session['available_capacity']) + " " + session['vaccine'] + " slots available on " + str(
                        session["date"]) + " at " + str(center["name"]) + ", " + str(center["address"]) + ", " + str(
                        center["district_name"]) + ", " + str(center["state_name"] + "\n\n")
                    messageContentShort = session['vaccine'] + " slots available-" + str(session["date"]) + "," + str(
                        center["state_name"] + "\n")
                    availableSlots.append(messageContent)
                    availableSlotsShort.append(messageContentShort)
    slots.append(availableSlots)
    slots.append(availableSlotsShort)

    print("Slots:")
    sys.stdout.flush()
    print(availableSlotsShort)
    sys.stdout.flush()

    return slots

def slotChecker():
    print("Started checking slots as per schedule")
    sys.stdout.flush()

    requests = Requests.query.all()

    checkByDistrictURL = "https://cdn-api.co-vin.in/api/v2/appointment/sessions/public/calendarByDistrict"
    IST = pytz.timezone('Asia/Kolkata')
    datetime_ist = datetime.now(IST)
    currentDate = str(datetime_ist.date().strftime('%d-%m-%Y'))

    headers = {'content-type': 'application/json',
               'origin':'https://www.cowin.gov.in',
               'referer':'https://www.cowin.gov.in/',
               'sec-ch-ua':'" Not A;Brand";v="99", "Chromium";v="90", "Google Chrome";v="90"',
               'user-agent': "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36"}

    if len(requests)>0:
        for request in requests:
            dist = request.district_code
            hitURL = checkByDistrictURL + "?district_id=" + str(dist) + "&date=" + currentDate
            print(hitURL)
            sys.stdout.flush()
            response = r.get(hitURL, headers=headers)
            print("response is : ")
            sys.stdout.flush()
            print(response)
            sys.stdout.flush()
            availableSlots = []
            if response:
                availableSlots = checkDetails(response.content.decode("utf-8"), request.age ,request.vaccine_type, request.dose)

                if (len(availableSlots[0]) > 0):
                    try:
                        sendEmail(availableSlots[0], request.mail_id)
                        if(request.mobile_number):
                            sendText(availableSlots[1], request.mobile_number)
                    except Exception as e:
                        print("ERROR while sending SMS or Email")
                        print(e)
                        sys.stdout.flush()


if __name__ == "__main__":        # on running python app.py
    scheduler = BackgroundScheduler()
    scheduler.add_job(func=slotChecker, trigger="interval", seconds=30)
    scheduler.start()
    atexit.register(lambda: scheduler.shutdown())

    slotChecker()

    app.run()                     # run the flask app

