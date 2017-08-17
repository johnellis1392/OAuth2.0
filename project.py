from flask import Flask, render_template, request, redirect,jsonify, url_for, flash
app = Flask(__name__)

from sqlalchemy import create_engine, asc
from sqlalchemy.orm import sessionmaker
from database_setup import Base, Restaurant, MenuItem, User


# Import flask session setup
from flask import session as login_session
import random, string

from oauth2client.client import flow_from_clientsecrets
from oauth2client.client import FlowExchangeError
import httplib2
import json
from flask import make_response
import requests


# Get client secrets for server configuration.
# NOTE: You get this json file from google cloud
# by going to console.developers.google.com/apis.credentials
# and downloading the client id that goes with
# your app.
CLIENT_ID = json.loads(open('client_secrets.json', 'r').read())['web']['client_id']


#Connect to Database and create database session
engine = create_engine('sqlite:///restaurantmenu.db')
Base.metadata.bind = engine

DBSession = sessionmaker(bind=engine)
session = DBSession()

# @app.route('/test')
# def testJSON():
#     return jsonify({'message': 'Hello, World!'})





# Login route
@app.route('/login')
def showLogin():
    # Generate random state token
    state = ''.join(random.choice(string.ascii_uppercase + string.digits) for x in xrange(32))

    # Store state token
    login_session['state'] = state

    # return "The current session state is %s" % login_session['state']
    return render_template('login.html', STATE=state)


# Create a json error response
def __json_response(message, status):
    response = make_response(json.dumps(message), status)
    response.headers['Content-Type'] = 'application/json'
    return response


# Google account connection endpoint
@app.route('/gconnect', methods=['POST'])
def gconnect():
    # Verify state token
    print " *** Entering callback..."
    if request.args.get('state') != login_session['state']:
        return __json_response('Invalid State Token', 401)

    code = request.data
    try:
        oauth_flow = flow_from_clientsecrets('client_secrets.json', scope = '')
        oauth_flow.redirect_uri = 'postmessage'
        credentials = oauth_flow.step2_exchange(code)
    except FlowExchangeError:
        return __json_response('Failed to upgrade the authorization code.', 401)

    # Get access token
    access_token = credentials.access_token
    url = ('https://www.googleapis.com/oauth2/v1/tokeninfo?access_token=%s' % access_token)

    # Send request to google to verify access_token
    h = httplib2.Http()
    result = json.loads(h.request(url, 'GET')[1])


    # If result contains errors, return a 500
    if result.get('error') is not None:
        return __json_response(result.get('error'), 500)


    # Now get the google plus id from the response
    gplus_id = credentials.id_token['sub']
    if result['user_id'] != gplus_id:
        return __json_response("Token's user id doesn't match the given user id.", 401)


    # Verify ClientID issued from google-plus
    if result['issued_to'] != CLIENT_ID:
        return __json_response("Token's client id doesn't match the app's client id.", 401)


    # Check if user is already logged in
    stored_credentials = login_session.get('credentials')
    stored_gplus_id = login_session.get('gplus_id')
    if stored_credentials is not None and gplus_id == stored_gplus_id:
        return __json_response('Current user is already connected.', 200)


    # If none of the above statements were correct, we have a valid access_token
    login_session['credentials'] = credentials
    login_session['gplus_id'] = gplus_id

    # Fetch user info
    userinfo_url = "https://www.googleapis.com/oauth2/v1/userinfo"
    params = { 'access_token': credentials.access_token, '': 'json' }
    answer = requests.get(userinfo_url, params = params)
    data = json.loads(answer.text)

    # Get relevant data for our app
    login_session['username'] = data['name']
    login_session['picture'] = data['picture']
    login_session['email'] = data['email']


    # Check if user already exists. If user exists, store
    # that user's information in the login session. If not,
    # create a new user object for the user's information.
    user_id = getUserInfo(email = login_session['email'])
    if user_id == None:
        user_id = createUser(login_session)
    login_session['user_id'] = user_id


    output = '<h1>Welcome, ' + login_session['username'] + '!</h1>'
    flash('you are now logged in as %s' % login_session['username'])
    return output
    


# Endpoint for logging out
@app.route('/gdisconnect')
def gdisconnect():
    credentials = login_session.get('credentials')
    if credentials is None:
        return __json_response('Current user is not connected.', 401)

    # Get access token and send to google to revoke
    access_token = credentials.access_token
    url = 'https://accounts.google.com/o/oauth2/revoke?token=%s' % access_token
    h = httplib2.Http()
    result = h.request(url, 'GET')[0]

    # If we get a 200, revokation was successful
    if result['status'] == '200':

        # Delete stored user information
        del login_session['credentials']
        del login_session['gplus_id']
        del login_session['username']
        del login_session['email']
        del login_session['picture']

        return __json_response('Successfully Disconnected.', 200)

    else:
        # Something went wrong
        return __json_response('Failed to revoke token for given user.', 400)







#JSON APIs to view Restaurant Information
@app.route('/restaurant/<int:restaurant_id>/menu/JSON')
def restaurantMenuJSON(restaurant_id):
    restaurant = session.query(Restaurant).filter_by(id = restaurant_id).one()
    items = session.query(MenuItem).filter_by(restaurant_id = restaurant_id).all()
    return jsonify(MenuItems=[i.serialize for i in items])


@app.route('/restaurant/<int:restaurant_id>/menu/<int:menu_id>/JSON')
def menuItemJSON(restaurant_id, menu_id):
    Menu_Item = session.query(MenuItem).filter_by(id = menu_id).one()
    return jsonify(Menu_Item = Menu_Item.serialize)

@app.route('/restaurant/JSON')
def restaurantsJSON():
    restaurants = session.query(Restaurant).all()
    return jsonify(restaurants= [r.serialize for r in restaurants])


#Show all restaurants
@app.route('/')
@app.route('/restaurant/')
def showRestaurants():
    restaurants = session.query(Restaurant).order_by(asc(Restaurant.name))
    if 'username' not in login_session:
        return render_template('restaurants.html', restaurants = restaurants)
    else:
        return render_template('publicrestaurants.html', restaurants = restaurants)


#Create a new restaurant
@app.route('/restaurant/new/', methods=['GET','POST'])
def newRestaurant():
  if 'username' not in login_session:
    return redirect('/login')
  if request.method == 'POST':
      newRestaurant = Restaurant(name = request.form['name'], user_id = login_session['user_id'])
      session.add(newRestaurant)
      flash('New Restaurant %s Successfully Created' % newRestaurant.name)
      session.commit()
      return redirect(url_for('showRestaurants'))
  else:
      return render_template('newRestaurant.html')

#Edit a restaurant
@app.route('/restaurant/<int:restaurant_id>/edit/', methods = ['GET', 'POST'])
def editRestaurant(restaurant_id):
  if 'username' not in login_session:
    return redirect('/login')

  editedRestaurant = session.query(Restaurant).filter_by(id = restaurant_id).one()
  if request.method == 'POST':
      if request.form['name']:
        editedRestaurant.name = request.form['name']
        flash('Restaurant Successfully Edited %s' % editedRestaurant.name)
        return redirect(url_for('showRestaurants'))

  else:
      return render_template('editRestaurant.html', restaurant = editedRestaurant)


#Delete a restaurant
@app.route('/restaurant/<int:restaurant_id>/delete/', methods = ['GET','POST'])
def deleteRestaurant(restaurant_id):
  if 'username' not in login_session:
    return redirect('/login')

  restaurantToDelete = session.query(Restaurant).filter_by(id = restaurant_id).one()
  if restaurantToDelete.user_id != login_session['user_id']:
    return __json_response('You are not authorized to perform this operation.', 401)

  if request.method == 'POST':
    session.delete(restaurantToDelete)
    flash('%s Successfully Deleted' % restaurantToDelete.name)
    session.commit()
    return redirect(url_for('showRestaurants', restaurant_id = restaurant_id))
  else:
    return render_template('deleteRestaurant.html',restaurant = restaurantToDelete)


#Show a restaurant menu
@app.route('/restaurant/<int:restaurant_id>/')
@app.route('/restaurant/<int:restaurant_id>/menu/')
def showMenu(restaurant_id):
    restaurant = session.query(Restaurant).filter_by(id = restaurant_id).one()
    creator = getUserInfo(restaurant.user_id)
    items = session.query(MenuItem).filter_by(restaurant_id = restaurant_id).all()

    if 'username' not in login_session or creator.id != login_session['user_id']:
        return render_template('publicmenu.html', items = items, restaurant = restaurant)
    else:
        return render_template('menu.html', items = items, restaurant = restaurant)
     


#Create a new menu item
@app.route('/restaurant/<int:restaurant_id>/menu/new/',methods=['GET','POST'])
def newMenuItem(restaurant_id):
  if 'username' not in login_session:
    return redirect('/login')

  restaurant = session.query(Restaurant).filter_by(id = restaurant_id).one()

  if request.method == 'POST':
      newItem = MenuItem(name = request.form['name'], description = request.form['description'], price = request.form['price'], course = request.form['course'], restaurant_id = restaurant_id, user_id = restaurant.user_id)
      session.add(newItem)
      session.commit()
      flash('New Menu %s Item Successfully Created' % (newItem.name))
      return redirect(url_for('showMenu', restaurant_id = restaurant_id))

  else:
      return render_template('newmenuitem.html', restaurant_id = restaurant_id)


#Edit a menu item
@app.route('/restaurant/<int:restaurant_id>/menu/<int:menu_id>/edit', methods=['GET','POST'])
def editMenuItem(restaurant_id, menu_id):
  if 'username' not in login_session:
    return redirect('/login')

  editedItem = session.query(MenuItem).filter_by(id = menu_id).one()
  restaurant = session.query(Restaurant).filter_by(id = restaurant_id).one()

  if request.method == 'POST':
      if request.form['name']:
          editedItem.name = request.form['name']
      if request.form['description']:
          editedItem.description = request.form['description']
      if request.form['price']:
          editedItem.price = request.form['price']
      if request.form['course']:
          editedItem.course = request.form['course']
      session.add(editedItem)
      session.commit() 
      flash('Menu Item Successfully Edited')
      return redirect(url_for('showMenu', restaurant_id = restaurant_id))

  else:
      return render_template('editmenuitem.html', restaurant_id = restaurant_id, menu_id = menu_id, item = editedItem)


#Delete a menu item
@app.route('/restaurant/<int:restaurant_id>/menu/<int:menu_id>/delete', methods = ['GET','POST'])
def deleteMenuItem(restaurant_id,menu_id):
    if 'username' not in login_session:
        return redirect('/login')

    restaurant = session.query(Restaurant).filter_by(id = restaurant_id).one()
    itemToDelete = session.query(MenuItem).filter_by(id = menu_id).one() 

    if restaurant.user_id != login_session['user_id']:
        return __json_response('You are not authorized to perform this operation.', 401)

    if request.method == 'POST':
        session.delete(itemToDelete)
        session.commit()
        flash('Menu Item Successfully Deleted')
        return redirect(url_for('showMenu', restaurant_id = restaurant_id))

    else:
        return render_template('deleteMenuItem.html', item = itemToDelete)




# Get the if for the user account associated with the given email
def getUserID(email):
    try:
        user = session.query(User).filter_by(email = email).one()
        return user.id
    except:
        return None


# Get information for a user by the user's id
def getUserInfo(user_id):
    user = session.query(User).filter_by(id = user_id).one()
    return user


# Helper method for creating new users
def createUser(login_session):

    # Create new user from login session data
    newUser = User(name = login_session['usernmae'], email = login_session['email'], picture = login_session['picture'])
    session.add(newUser)
    session.commit()

    # Query current user session for user information
    user = session.query(User).filter_by(email = login_session['email']).one()
    return user.id



if __name__ == '__main__':
  app.secret_key = 'super_secret_key'
  app.debug = True
  app.run(host = '0.0.0.0', port = 5000)
