"""
ECE 5725, Fall 2017
"Grocery Guard"
Cameron Schultz (cjs342) and Dev Sanghvi (dys27)
December 7, 2017
Description: This code drives the front end user interface for the Grocery Guard
             device. Communicates with a PostgreSQL back end stored locally on
             the Raspberry Pi. Code should be run with no arguments on the Raspberry
             Pi device that contains the database. UI animation screens are under the 
             "User Interface Methods"section. Backend communication, set interpretation, 
             and other helper methods are under the "Functional Methods" section.
External packages used:
      - numpy
      - pygame
      - zbar
      - psycopg2
      - RPi.GPIO
"""

import os
import pygame
from pygame.locals import *
import pygame.camera
import pygame.surfarray
import numpy as np
import zbar
import zbar.misc
import time
import psycopg2
import datetime
from subprocess import call
import RPi.GPIO as GPIO

# Initialize Environment Variables for TFT
os.putenv('SDL_VIDEODRIVER','fbcon')
os.putenv('SDL_FBDEV','/dev/fb1')
os.putenv('SDL_MOUSEDRV','TSLIB')
os.putenv('SDL_MOUSEDEV','/dev/input/touchscreen')

pygame.init()

# Hide mouse on touchscreen
pygame.mouse.set_visible(False)


#Globals
SIZE = WIDTH, HEIGHT = 320,240            #PiTFT Resolution

BLACK = [0, 0, 0]
RED = [255, 0, 0]
GREEN = [0, 255, 0]
BLUE = [0, 0, 255]
WHITE = [255, 255, 255]

CAM_NAME='/dev/video0'
CAM_RES=(640,480)  # webcam resolution

screen = pygame.display.set_mode(SIZE)
WINDOW = 62 #display margins for text alignement

# Set up GPIO 27 as "bailout" to desktop
GPIO.setmode(GPIO.BCM)
GPIO.setup(27, GPIO.IN, pull_up_down=GPIO.PUD_UP)
def GPIO27_callback(channel):
   cmd = 'startx'
   call(cmd, shell=True)

# Add threaded callback interrupt for GPIO 27
GPIO.add_event_detect(27,GPIO.FALLING,callback=GPIO27_callback,bouncetime=300)

# --------------- User Interface Methods ---------------- #

def home_screen():
   """
   Animates the home screen for the Grocery Guard. Called on startup.
   Continuously polls scan() to see if barcode detected.
   Links to display_notifications, display_fridge, and display_recipes.
   Power button in bottom right shuts down the pi.
   """

   my_font = pygame.font.Font(None,40)
   my_buttons = {'Display Items':(WIDTH/2,50),
               'Suggest Recipes':(WIDTH/2,100),
               'Notifications':(WIDTH/2,150)}

   pos = (0,0) # mouse position on click

   start_time = time.time()
   delay = 100 # barcode scanning interval

   # animate and get events
   while True:
      # mouse/touchscreen input
      for event in pygame.event.get():
         if(event.type is MOUSEBUTTONDOWN):
            pos=pygame.mouse.get_pos()
         # detect mouse clicks (trigger event when mouse released)
         elif(event.type is MOUSEBUTTONUP):
            pos=pygame.mouse.get_pos()
            x,y=pos
            #power button
            if y>210:
               if x>290:
                  # shut down the pi
                  cmd = 'sudo shutdown -h now'
                  call(cmd, shell=True)
            #Display Items
            elif 25<y<75:
               ingredients = get_ingredients()
               display_fridge(ingredients,0)
            #Suggest Recipes
            elif 75<y<125:
               recipes = get_recipes()
               display_recipes(recipes)
            #Display Notifications
            elif 125<y<175:
               ingredients = get_ingredients()
               notifications = get_notifications(ingredients)
               display_notifications(notifications,0)

      screen.fill(BLACK) # Erase the Work space

      #write text to screen
      for my_text,text_pos in my_buttons.items():
         text_surface = my_font.render(my_text, True, WHITE)
         text_rect = text_surface.get_rect(center=text_pos)
         screen.blit(text_surface,text_rect)

      # draw power button
      pygame.draw.circle(screen, RED, [WIDTH-15,HEIGHT-15],15)
      pygame.draw.circle(screen, WHITE, [WIDTH-15,HEIGHT-15],12,2)
      pygame.draw.rect(screen, WHITE, (WIDTH-16,HEIGHT-32,2,14))
      
      pygame.display.flip() # display workspace on screen
      
      # poll scan() for barcode hits
      if delay == 0:
         id = scan()
         if id > 0:
            print str(id) + " scanned"
            item = get_item_name(id)
            print item, type(item)
            display_item_added(item,id)
         # reset scanning interval timer
         delay = 100
         start_time=time.time()
      
      delay -= 1

def display_fridge(ingredients,starti):
   """
   Animates and displays the contents currently contained in the 'Fridge.' These items 
   are scanned in using the barcode scanner.
   ingredients must be formatted as a numpy array:
      ingredients = np.asarray([ing1,ing2,ing3,...])
      where ingi = "Name amt+unit time to expire in days"
   starti is the index of ingredients from which to begin displaying
   User may delete expired ingredients in their Fridge from this screen.
   Links to home_screen(), display_notifications(), display_recipes()
   """
   
   my_font = pygame.font.Font(None,30)
   my_font2 = pygame.font.Font(None,20)

   # text display dictionaries
   ing_list = {}
   amt_list={}
   exp_list={}
   circle_list = {}
   text_list={"Item                 Amount      Expiring in":((WIDTH/2),10)}
   text_list["-"*WINDOW]=((WIDTH/2),20)
   NUM_ING = 8 #number of ingredient to display per screen

   # add each of the NUM_ING ingredients to the list
   # add ingredients[starti:starti+NUM_ING]
   for i in range(min(ingredients.shape[0]-starti,NUM_ING)):
      #parse ingredient
      tmp = ingredients[starti+i]
      tmp_list = tmp.split()
      
      # for all text-based dictionaries, entries are appended with a unique
      # number of whitespaces to make each key unique
      # structure of entries is dict["text to display"] = (posx, posy)
      ing_list[" ".join(tmp_list[:-4]) + " "*(i+1)] = ((WIDTH/2),30+20*i)
      amt_list[tmp_list[-4] + " "*(i+1)] = ((WIDTH/2),30+20*i)
      exp_list[tmp_list[-3] + " days" + " "*(i+1)] = ((WIDTH/2),30+20*i)

      # if ingredient expired, draw circle at its position
      if float(tmp_list[-3]) < 0:
         circle_list[" ".join(tmp_list[:-4])+ " "*(i+1)] = ((WIDTH-15),30+20*i)
      
   # determine if there are more ingredients to display after/before this screen
   more = True if ingredients.shape[0]-starti > NUM_ING else False
   prev = True if starti > NUM_ING-1 else False
   # add buttons accordingly
   if more:
      ing_list['More Ingredients'] = ((WIDTH/2),10+20*(NUM_ING+1)+5)
   elif prev:
      ing_list['Previous'] = ((WIDTH/2),10+20*(NUM_ING+1)+5)

   # add static buttons
   my_buttons = {'Menu':(50,220),
               'Suggest Recipes':(160,220),
               'Notifications':(270,220)}

   # position of mouse click
   pos = (0,0) 
   
   # animate and get events
   while True:
      #mouse/touchscreen input
      for event in pygame.event.get():
         if(event.type is MOUSEBUTTONDOWN):
            pos=pygame.mouse.get_pos()
         elif(event.type is MOUSEBUTTONUP):
            pos=pygame.mouse.get_pos()
            x,y=pos
            #check if circle clicked
            if x > WIDTH-50:
               for ing,pos in circle_list.items():
                  if pos[1]-15 < y < pos[1]+15:
                     #print "deleting " + ing
                     # delete item from Fridge
                     id = get_item_id(ing.strip())
                     update_fridge(id,0) # when 0 passed as arg[1], update_fridge deletes
                     #refresh ingredient list and display at same start index
                     new_ingredients = get_ingredients()
                     display_fridge(new_ingredients,starti)
            #more ingredients
            if 185<y<205:
               if more:
                  # display ingredients starti + NUM_ING thru starti + 2*NUM_ING-1
                  display_fridge(ingredients,starti+NUM_ING)
               elif prev:
                  # display ingredients starti-NUM_ING thru starti-1
                  display_fridge(ingredients,starti-NUM_ING)

            #Display static buttons
            if y>210:
               # back to menu
               if x<75:
                  home_screen()
               # Suggest Recipes
               elif 100<x<225:
                  recipes = get_recipes()
                  display_recipes(recipes)
               #Display Notifications
               elif x>230:
                  notifications = get_notifications(ingredients)
                  display_notifications(notifications,0)

      screen.fill(BLACK) # Erase the Work space

      # display text items
      for my_text,text_pos in text_list.items():
         text_surface = my_font2.render(my_text, True, WHITE)
         text_rect = text_surface.get_rect(center=text_pos)
         text_rect.left = 50
         screen.blit(text_surface,text_rect)

      for my_text,text_pos in my_buttons.items():
         text_surface = my_font2.render(my_text, True, WHITE)
         text_rect = text_surface.get_rect(center=text_pos)
         screen.blit(text_surface,text_rect)

      for my_text,text_pos in ing_list.items():
         text_surface = my_font2.render(my_text, True, WHITE)
         text_rect = text_surface.get_rect(center=text_pos)
         text_rect.left = 50
         screen.blit(text_surface,text_rect)

      for my_text,text_pos in amt_list.items():
         text_surface = my_font2.render(my_text, True, WHITE)
         text_rect = text_surface.get_rect(center=text_pos)
         text_rect.left = 170
         screen.blit(text_surface,text_rect)

      for my_text,text_pos in exp_list.items():
         text_surface = my_font2.render(my_text, True, WHITE)
         text_rect = text_surface.get_rect(center=text_pos)
         text_rect.left = 225
         screen.blit(text_surface,text_rect)
      #draw circles
      for index,pos in circle_list.items():
         pygame.draw.circle(screen, RED, pos,10)

      pygame.display.flip()

def display_recipes(recipes):
   """
   Animates and displays the suggested recipes. This list is determined by the 
   get_recipes() function.
   recipes is formatted as a numpy array
      recipes = np.asarray([rec1,rec2,...],[id1,id2,...])
      where reci = 'name %match'
      %match = (#ing in fridge used by recipe)/(# total ing used by recipe)
   """
   # parse recipes
   ids = recipes[1]
   recipes = recipes[0]

   text_list={"Recipe                          Percent Match":((WIDTH/2),10)}
   text_list["-"*WINDOW]=((WIDTH/2),20)
   
   my_font = pygame.font.Font(None,25)
   my_font2 = pygame.font.Font(None,20)
   rec_list = {}
   match_list = {}
   
   # dictionary of recipes unsorted_dict[recipe name] = %match
   unsorted_dict = {}
   for i in range(5):
      tmp = recipes[i]
      tmp_list = tmp.split()
      match = float(tmp_list[-1])*100
      var = ' '.join(tmp_list[:-1])
      unsorted_dict[var] = (match,ids[i])

   # sort the dictionary by %match
   sorted_list = sorted(unsorted_dict, key=unsorted_dict.get, reverse=True)
   
   i = 0 # index used to create unique keys
   # add elements of sorted_list to rec_list and match_list in order
   for ing in sorted_list:
      match = float(unsorted_dict[ing][0])
      if match >= 100:
         match_str = str(match)[:3]
      else:
         match_str = str(match)[:2]
      var = ing
      # if text too long, crop
      if len(var) > 18:
         var = var[:16] + '...'
      rec_list[var + " "*(i+1)] = ((WIDTH/2),35+33*i)
      match_list[match_str + "%"  + " "*(i+1)] = ((WIDTH/2),35+33*i)
      i+=1

   # static buttons
   my_buttons = {'Menu':(50,220),
               'Display Items':(160,220),
               'Notifications':(270,220)}

   # mouse position
   pos = (0,0) 
   
   # animate and get events
   while True:
      #mouse/touchscreen input
      for event in pygame.event.get():
         if(event.type is MOUSEBUTTONDOWN):
            pos=pygame.mouse.get_pos()
         elif(event.type is MOUSEBUTTONUP):
            pos=pygame.mouse.get_pos()
            x,y=pos
            #go to specific recipe screen
            if x>50:
               if 30<y<45:
                  # get appropriate recipe id 
                  display_single_recipe(unsorted_dict[sorted_list[0]][1])
               elif 55<y<80:
                  display_single_recipe(unsorted_dict[sorted_list[1]][1])
               elif 90<y<115:
                  display_single_recipe(unsorted_dict[sorted_list[2]][1])
               elif 120<y<145:
                  display_single_recipe(unsorted_dict[sorted_list[3]][1])
               elif 155<y<180:
                  display_single_recipe(unsorted_dict[sorted_list[4]][1])
            # Static buttons
            if y>210:
               #back to menu   
               if x<75:
                  home_screen()
               #Display Fridge
               elif 115<x<210:
                  ingredients = get_ingredients()
                  display_fridge(ingredients,0)
               #Display Notifications
               elif x>230:
                  ingredients = get_ingredients()
                  notifications = get_notifications(ingredients)
                  display_notifications(notifications,0)

      screen.fill(BLACK) # Erase the Work space
      # write text
      for my_text,text_pos in my_buttons.items():
         text_surface = my_font2.render(my_text, True, WHITE)
         text_rect = text_surface.get_rect(center=text_pos)
         screen.blit(text_surface,text_rect)

      for my_text,text_pos in rec_list.items():
         text_surface = my_font.render(my_text, True, WHITE)
         text_rect = text_surface.get_rect(center=text_pos)
         text_rect.left = 50
         screen.blit(text_surface,text_rect)

      for my_text,text_pos in match_list.items():
         text_surface = my_font.render(my_text, True, WHITE)
         text_rect = text_surface.get_rect(center=text_pos)
         text_rect.left = 230
         screen.blit(text_surface,text_rect)

      for my_text,text_pos in text_list.items():
         text_surface = my_font2.render(my_text, True, WHITE)
         text_rect = text_surface.get_rect(center=text_pos)
         text_rect.left = 50
         screen.blit(text_surface,text_rect)

      pygame.display.flip()

def display_notifications(notifications, starti):
   """
   Animates and displays the notifications screen. Notifications come from get_notifications()
   notifications is formatted as a numpy array
      notifications = np.asarray([not1,not2,...])
      where noti = "ingredient;message"
   starti is the starting index of notifications from which to display on this screen
   """
   
   my_font = pygame.font.Font(None,30)
   my_font2 = pygame.font.Font(None,20)

   text_list={"Item                 Message":((WIDTH/2),10)}
   text_list["-"*WINDOW]=((WIDTH/2),20)
   ing_list = {}
   not_list = {}
   circle_list = {}
   NUM_NOT = 8 #number of notifications to display per screen
   # parse notifcations and add to text lists
   for i in range(min(notifications.shape[0]-starti,NUM_NOT)):
      tmp = notifications[starti+i]
      tmp_list = tmp.split(";")
      ing_list[tmp_list[0]+" "*(i+1)] = ((WIDTH/2),30+20*i)
      not_list[tmp_list[1]+" "*(i+1)] = ((WIDTH/2),30+20*i)
      # if ingredient expired, draw a circle next to it
      if tmp_list[1][:7] == "expired":
         circle_list[tmp_list[0]+" "*(i+1)] = ((WIDTH-30),30+20*i)
   
   # determine if more notifications exist on next/prev screen
   more = True if notifications.shape[0]-starti > NUM_NOT else False
   prev = True if starti > NUM_NOT-1 else False
   # and add appropriate buttons
   if more:
      ing_list['More notifications'] = ((WIDTH/2),10+20*(NUM_NOT+1)+5)
   elif prev:
      ing_list['Previous'] = ((WIDTH/2),10+20*(NUM_NOT+1)+5)

   # add static buttons
   my_buttons = {'Menu':(50,220),
               'Suggest Recipes':(160,220),
               'Display Items':(270,220)}

   pos = (0,0) 
   
   # animate and get events
   while True:
      #mouse/touchscreen input
      for event in pygame.event.get():
         if(event.type is MOUSEBUTTONDOWN):
            pos=pygame.mouse.get_pos()
         elif(event.type is MOUSEBUTTONUP):
            pos=pygame.mouse.get_pos()
            x,y=pos
            #check if circle clicked
            if x > WIDTH-50:
               for ing,pos in circle_list.items():
                  if pos[1]-15 < y < pos[1]+15:
                     #print "deleting ", ing
                     # delete item from fridge
                     id = get_item_id(ing.strip())
                     update_fridge(id,0)
                     # refresh ingredients list
                     new_ingredients = get_ingredients()
                     new_notifications = get_notifications(new_ingredients)
                     display_notifications(new_notifications,starti)
            #more notifications
            if 185<y<205:
               if more:
                  # display notifications starti + NUM_NOT thru starti + 2*NUM_NOT-1
                  display_notifications(notifications,starti+NUM_NOT)
               elif prev:
                  # display notifications starti-NUM_NOT thru starti-1
                  display_notifications(notifications,starti-NUM_NOT)
            #Display Items
            if y>210:
               #back to menu   
               if x<75:
                  home_screen()
               #Suggest Recipes
               elif 100<x<225:
                  recipes = get_recipes()
                  display_recipes(recipes)
               #Display Fridge
               elif x>230:
                  ingredients = get_ingredients()
                  display_fridge(ingredients,0)

      screen.fill(BLACK) # Erase the Work space
      
      # display text items
      for my_text,text_pos in my_buttons.items():
         text_surface = my_font2.render(my_text, True, WHITE)
         text_rect = text_surface.get_rect(center=text_pos)
         screen.blit(text_surface,text_rect)

      for my_text,text_pos in not_list.items():
         text_surface = my_font2.render(my_text, True, WHITE)
         text_rect = text_surface.get_rect(center=text_pos)
         text_rect.left = 150
         screen.blit(text_surface,text_rect)

      for my_text,text_pos in ing_list.items():
         text_surface = my_font2.render(my_text, True, WHITE)
         text_rect = text_surface.get_rect(center=text_pos)
         text_rect.left = 50
         screen.blit(text_surface,text_rect)

      for my_text,text_pos in text_list.items():
         text_surface = my_font2.render(my_text, True, WHITE)
         text_rect = text_surface.get_rect(center=text_pos)
         text_rect.left = 50
         screen.blit(text_surface,text_rect)
      # draw circles
      for index,pos in circle_list.items():
         pygame.draw.circle(screen, RED, pos,10)

      pygame.display.flip()
   
def display_single_recipe(id):
   """
   Animates and displays the single recipe screen. The recipe to display is specified
   by its id. The id is extracted from the Postgres backend.
   User may "cook" the recipe, which subtracts the amounts used from the Fridge.
   Links to display_recipes(), display_instruction()
   """

   # connect to Postgres
   conn = psycopg2.connect('dbname=grocery_guard')
   cur = conn.cursor()

   # fetch name of recipe, ingredients used, amounts used, instructions, and image
   cur.execute("select name,ingredients,amounts,instructions,image from recipes where id = %s" %str(id))
   data = cur.fetchone()

   # parse data
   name = data[0]
   ingredients = data[1]
   quantities = data[2]
   instructions = data[3].split("\n") #instructions separated by line carriage in db
   #combine quantites and ingredients into amounts. This is what is displayed
   amounts=['']*len(ingredients)
   for i in range(len(ingredients)):
      print str(int(ingredients[i]))
      cur.execute("select name from codes where id = %s" % str(int(ingredients[i])))
      amounts[i] = str(quantities[i]) + ' ' + cur.fetchone()[0]
   
   recipe = np.asarray([[name.title()],instructions,amounts])

   my_font = pygame.font.Font(None,26)
   my_font2 = pygame.font.Font(None,20)

   text_list={recipe[0][0]:((WIDTH/2),10)}
   text_list["-"*WINDOW]=((WIDTH/2),20)
   text_list["Ingredients:"]=((WIDTH/2),30)
   text_list2={}
   # separate ingredients+amounts into two columns
   for i in range(len(amounts)):
      if i < 6:
         text_list[amounts[i]+" "*(i+1)] = ((WIDTH/2),50+20*i)
      else:
         text_list2[amounts[i]+" "*(i+1)] = ((WIDTH/2),50+20*(i-6))

   # static buttons
   my_buttons = {'Show Instructions':(75,220),
               'Back to Recipes':(250,220)}

   pos = (0,0) 

   #close connection
   cur.close()
   conn.close()
   cooked = False

   # animate and get events
   while True:
      #mouse/touchscreen input
      for event in pygame.event.get():
         if(event.type is MOUSEBUTTONDOWN):
            pos=pygame.mouse.get_pos()
         elif(event.type is MOUSEBUTTONUP):
            pos=pygame.mouse.get_pos()
            x,y=pos
            #cook recipe
            if y > 170 and 130<x<190 and not cooked:
               #note: cooked variable allows recipe to be cooked only a single time
               cooked = True
               # subtract amounts used from fridge
               for i in range(len(ingredients)):
                  #print ingredients[i], quantities[i]
                  update_fridge(ingredients[i],quantities[i])
            # static buttons
            if y>210:
               #back to menu   
               if x<140:
                  display_instruction(instructions,0,id,False)
               #suggest recipes
               elif x>190:
                  recipes = get_recipes()
                  display_recipes(recipes)

      screen.fill(BLACK) # Erase the Work space
      # display text
      for my_text,text_pos in my_buttons.items():
         text_surface = my_font2.render(my_text, True, WHITE)
         text_rect = text_surface.get_rect(center=text_pos)
         screen.blit(text_surface,text_rect)
      
      for my_text,text_pos in text_list.items():
         text_surface = my_font2.render(my_text, True, WHITE)
         text_rect = text_surface.get_rect(center=text_pos)
         text_rect.left = 50
         screen.blit(text_surface,text_rect)
      for my_text,text_pos in text_list2.items():
         text_surface = my_font2.render(my_text, True, WHITE)
         text_rect = text_surface.get_rect(center=text_pos)
         text_rect.left = 175
         screen.blit(text_surface,text_rect)

      # determine button properties depending on if cooked or not
      if not cooked:
         text = "COOK!"
         button_color = RED
      else:
         text = "COOKED!"
         button_color = GREEN

      # draw cook/cooked button
      pygame.draw.circle(screen, button_color, [WIDTH/2,HEIGHT-40],30)
      text_surface = my_font2.render(text, True, WHITE)
      text_rect = text_surface.get_rect(center=(WIDTH/2,HEIGHT-40))
      screen.blit(text_surface,text_rect)
      pygame.display.flip()
   
def display_instruction(instructions,starti,id,s):
   """
   Display a single instruction in a recipe.
   instructions contains the full list of instructions
   starti indicates the index within instructions to display
   id is the id of the recipe from which the instruction is taken
   s is a Boolean indicating whether or not speaking is enabled
   """
   
   # define speaking bash command
   cmd_beg = 'espeak -s150 ' 
   cmd_end = ' | aplay /home/pi/GroceryGuard/Text.wav 2>/dev/null &'
   cmd_out = '--stdout > /home/pi/GroceryGuard/Text.wav '
   
   # replace spaces with _ in instruction text so epseak can interpret
   instructions1 = instructions[starti].replace(' ','_')
   my_font = pygame.font.Font(None,30)
   my_font2 = pygame.font.Font(None,20)

   text_list={"Step " + str(starti+1):((WIDTH/2),10)}
   text_list["-"*(WINDOW+5)]=((WIDTH/2),20)

   #parse step and add to text_list
   instr = instructions[starti]
   wndw = WINDOW-25 # truncated text margin window
   
   #determine the number of blocks used to display the instruction
   blocks = int(np.ceil(float(len(instr))/(wndw)))
   for i in range(blocks):
      text = instr[wndw*i:wndw*(i+1)].strip()
      text_list[text + " "*(i+1)]=((WIDTH/2),30+20*i)

   # determine if more instructions exist on next/prev screen
   more = True if starti+1 < len(instructions)-1 else False
   prev = True if starti != 0 else False
   
   # static buttons
   my_buttons = {'Back to Recipe':(160,220)}
   speech_button={'Toggle Speech':((WIDTH-50),10)}

   if more:
      my_buttons["Next Step"] = (270,220)
   if prev:
      my_buttons["Previous Step"] = (50,220)

   
   pos = (0,0) 
   first=True # first time through loop. Should call speak only on this iteration
   speak = s
   
   # animate screen and get inputs
   while True:
      button_color = GREEN if speak else RED
      #mouse/touchscreen input
      for event in pygame.event.get():
         if(event.type is MOUSEBUTTONDOWN):
            pos=pygame.mouse.get_pos()
         elif(event.type is MOUSEBUTTONUP):
            pos=pygame.mouse.get_pos()
            x,y=pos
            
            if y>210:
               #previous step  
               if x<100 and prev:
                  call("kill -9 $(pgrep aplay)",shell=True) #stop speaking
                  display_instruction(instructions,starti-1,id,speak)
               # back to recipe screen
               elif 100<x<225:
                  call("kill -9 $(pgrep aplay)",shell=True) #stop speaking
                  display_single_recipe(id)
               # next step
               elif x>230 and more:
                  call("kill -9 $(pgrep aplay)",shell=True) # stop speaking
                  display_instruction(instructions,starti+1,id,speak)
            #toggle speech
            if y<20 and x>220:
               # enable
               if speak == False:
                  speak = True
                  first = True
               # disable
               else:
                  call("kill -9 $(pgrep aplay)",shell=True) # stop speaking
                  speak = False
                  first = False

      screen.fill(BLACK) # Erase the Work space

      # display text items
      for my_text,text_pos in my_buttons.items():
         text_surface = my_font2.render(my_text, True, WHITE)
         text_rect = text_surface.get_rect(center=text_pos)
         screen.blit(text_surface,text_rect)

      for my_text,text_pos in speech_button.items():
         text_surface = my_font2.render(my_text, True, button_color)
         text_rect = text_surface.get_rect(center=text_pos)
         screen.blit(text_surface,text_rect)

      for my_text,text_pos in text_list.items():
         text_surface = my_font2.render(my_text, True, WHITE)
         text_rect = text_surface.get_rect(center=text_pos)
         text_rect.left = 25
         screen.blit(text_surface,text_rect)

      pygame.display.flip()
      # start speaking
      if first and speak:
         call([cmd_beg+cmd_out+'"'+str(instructions1)+'"'+cmd_end], shell=True)
         first=False
   
def display_item_added(item,id):
   """
   Animates and displays the item added screen.
   item is the name of the ingredient, and id is its id.
   Called from home_screen() after the id of the scanned barcode has been obtained.
   User specifies if correct and should be added to the Fridge
   """
   
   my_font = pygame.font.Font(None,30)
   my_font2 = pygame.font.Font(None,20)
   
   # header
   text_list={"Item Added!":((WIDTH/2),10)}
   text_list["-"*WINDOW]=((WIDTH/2),20)

   # body
   text_list2={item.title() + " added":((WIDTH/2),100)}
   
   #static buttons
   my_buttons = {'Incorrect?':(75,220),
               'Correct?':(250,220)}

   pos = (0,0) 
   
   # animate and get events
   while:
      #mouse/touchscreen input
      for event in pygame.event.get():
         if(event.type is MOUSEBUTTONDOWN):
            pos=pygame.mouse.get_pos()
         elif(event.type is MOUSEBUTTONUP):
            pos=pygame.mouse.get_pos()
            x,y=pos
            #Display Items
            if y>210:
               # back to menu   
               if x<140:
                  home_screen()
               # add the fridge and return to menu
               elif x>190:
                  add_to_fridge(id)
                  home_screen()

      screen.fill(BLACK) # Erase the Work space
      # display text items
      for my_text,text_pos in my_buttons.items():
         text_surface = my_font2.render(my_text, True, WHITE)
         text_rect = text_surface.get_rect(center=text_pos)
         screen.blit(text_surface,text_rect)

      for my_text,text_pos in text_list.items():
         text_surface = my_font2.render(my_text, True, WHITE)
         text_rect = text_surface.get_rect(center=text_pos)
         text_rect.left = 50
         screen.blit(text_surface,text_rect)

      for my_text,text_pos in text_list2.items():
         text_surface = my_font.render(my_text, True, WHITE)
         text_rect = text_surface.get_rect(center=text_pos)
         screen.blit(text_surface,text_rect)

      pygame.display.flip()

# ---------------- Functional methods ---------------- #

def scan():
   """
   return UPC number if barcode detected. Return -1 if no barcode detected.
   called from home_screen at regular intervals
   """
   #initialize camera
   pygame.init()
   pygame.camera.init()
   pygame.camera.list_cameras()
   cam = pygame.camera.Camera(CAM_NAME, CAM_RES,'RGB')
   
   # sometimes, USB camera is detected at /dev/video0, other times at /dev/video1
   try:
      cam.start()
   except:
      cam = pygame.camera.Camera('/dev/video1', CAM_RES,'RGB')
      cam.start()

   time.sleep(0.5) 
   pygame_screen_image = cam.get_image() #get the image
   cam.stop()

   img_arr = pygame.surfarray.array3d(pygame_screen_image)
   
   #convert to grayscale and cast to uint8 so zbar can interpret
   img_arr = np.dot(img_arr[...,:3], [0.299, 0.587, 0.114])
   img_arr=img_arr.astype(np.uint8)
   
   #now that we have the image, scan for a barcode
   scanner = zbar.Scanner()
   results = scanner.scan(img_arr)
   if results==[]:
      print "no barcode found"
      return -1
   else:
      for result in results:
         # By default zbar returns barcode data as byte array, so decode byte array$
         #print(result.type, result.data.decode("ascii"), result.quality)
         return int(result.data.decode("ascii")) #return just the code as an int
   
def get_item_name(id):
   """
   Gets the name of an item id from Postgres
   """
   id = str(int(id)) # eliminate trailing decimals and cast to string
   # connect to db
   conn = psycopg2.connect('dbname=grocery_guard')
   cur = conn.cursor()
   # select name and quantity from barcodes table
   cur.execute("select name,quantity from codes where id = %s" % id)
   data = np.asarray(cur.fetchone())
   name = data[0]
   
   #close connection
   cur.close()
   conn.close()
   return name.title()

def get_item_id(name):
   """
   Gets the id of an item name from Postgres
   """
   # connect to db
   conn = psycopg2.connect('dbname=grocery_guard')
   cur = conn.cursor()
   # select id from barcodes db
   cur.execute("select id from codes where name ='%s'" % name.lower())
   data = np.asarray(cur.fetchone())
   id = data[0]
   
   # close connection
   cur.close()
   conn.close()
   return id

def add_to_fridge(id):
   """
   Add an item id to the Fridge. Gets name, amount, exp length from codes table 
   and writes to fridge. Called from home_screen after a valid barcode is detected
   and confirmed by the user.
   """
   id = str(int(id))
   # connect to db
   conn = psycopg2.connect('dbname=grocery_guard')
   cur = conn.cursor()
   # get name, amount, expiration length from codes
   cur.execute("select name,quantity,exp_days from codes where id = %s" % id)
   data = np.asarray(cur.fetchone())
   name = data[0]
   # convert strings to ints
   quantity = int(float(data[1]))   #amounts
   exp_days = int(float(data[2]))   #expiration length
   added = "date '" + str(datetime.date.today()) + "'" #date added
   
   #check if already in fridge
   cur.execute("select exists(select 1 from fridge where id = %s)" % id)
   exists = cur.fetchone()[0]
   # add amount to existing row
   if exists:
      cur.execute("select quantity from fridge where id = %s" % id)
      amt = int(cur.fetchone()[0]+quantity)
      msg = "update fridge set quantity = %s where id = %s" %(amt,id)
   # insert new row
   else:
      # write to fridge id, name, quantity, added, exp_days
      msg = "insert into fridge values (%s, '%s', %s, %s, %s)" % (id,name,quantity,added,exp_days)
   cur.execute(msg)

   # commit the write
   conn.commit()

   # close connection
   cur.close()
   conn.close()

def update_fridge(id,amt):
   """
   Subtract an item quantity from the Fridge. Subtract amt from current amount of ingredient
   id stored in the Fridge.
   If amt<=0, then delete the ingredient from the fridge.
   """
   
   id = str(int(id))
   # connect to the db
   conn = psycopg2.connect('dbname=grocery_guard')
   cur = conn.cursor()
   
   #check if ingredient in fridge
   cur.execute("select exists(select 1 from fridge where id = %s)" % id)
   exists = cur.fetchone()[0]
   if exists:
      # get amount currently in fridge
      cur.execute("select quantity from fridge where id = %s" % id)
      quantity = int(np.asarray(cur.fetchone())[0])
      # calculate the new amount
      if amt > 0:
         new_amt = int(quantity-amt)
      else:
         # if this update brings quantity negative, flag
         new_amt = -1

      #remove from fridge
      if new_amt <= 0:
         cur.execute("delete from fridge where id = %s" % id)
      #update fridge with new value
      else:
         cur.execute("update fridge set quantity = %s where id = %s" % (str(new_amt),id))

      #commit write
      conn.commit()

   # close connection
   cur.close()
   conn.close()

def get_ingredients():
   """
   Get list of ingredients and amounts currently contained in the Fridge.
   Queries Postgres 'fridge' table and formats ingredients as a numpy array.
   Format of each entry is np.asarray([ing1,ing2,...])
   where ingi = "Name amt+unit time to expire in days"
   """
   
   # connect to db
   conn = psycopg2.connect('dbname=grocery_guard')
   cur = conn.cursor()
   # get name + amt + exp length + date added
   cur.execute("select name,quantity,added,exp_days from fridge")
   f = np.asarray(cur.fetchall())
   ingredients = np.asarray([])
   # parse query and format
   for ing in f:
      name = ing[0]
      quantity = ing[1]
      added = ing[2]
      exp_on = added + datetime.timedelta(ing[3])
      days_to_exp = exp_on - datetime.date.today()

      msg = ' '.join([name,str(int(quantity)),str(days_to_exp)])
      ingredients = np.append(ingredients,msg)
   
   # close connection
   cur.close()
   conn.close()
   return ingredients
   
def get_recipes():
   """
   Get the top 5 matching recipes based on the ingredients currently in the Fridge.
   Formats each recipe as np.asarray([[recipe1,recipe2,...],[id1,id2,...]])
   where recipei = 'name %match'
   %match = #ing in fridge used by recipe/# total ing used by recipe
   """

   # initialize max overlap recipe tracking arrays
   max_recipes = np.asarray([0,0,0,0,0])  #IDs of max overlap recipes
   max_overlap = np.asarray([0,0,0,0,0])

   # connect tp db
   conn = psycopg2.connect('dbname=grocery_guard')
   cur = conn.cursor()
   # get all item ids from fridge (as UPC numbers)
   cur.execute("select id from fridge")
   I = np.asarray(cur.fetchall())
   # get all recipe ids from fride
   cur.execute("select id from recipes")
   recipes = np.asarray(cur.fetchall())
   
   #get max recipe ID to use as loop control
   cur.execute("select id from recipes where id = (select max(id) from recipes)")
   num_recs = int(cur.fetchone()[0])
   
   # Determine amount of overlap with Fridge for each recipe in db
   for r in range(1,num_recs+1):
      # get ingredients+amounts from recipe r
      cur.execute("select ingredients from recipes where id = %s" % str(r))
      ri = np.asarray(cur.fetchone())[0]  #ingredients for recipe r
      cur.execute("select amounts from recipes where id = %s" % str(r))
      ra = np.asarray(cur.fetchone())[0]  #amounts for recipe r
      
      # calculate the size of the overlap based on id
      s = np.intersect1d(ri,I)
      n = s.size

      # if we don't contain enough of an ingredient, subtract from the size of the overlap
      for i in s:
         # get index of i in recipe r's ingredient list
         # ra[indr] = amount of ingredient i recipe r requires
         indr = np.where(ri==i)[0][0] # index of i in r's ingredient list
         
         # get amount of ingredient id from fridge
         cur.execute("select quantity from fridge where id = %s" % str(int(i)))
         tmp = cur.fetchone()[0]
         
         # if amount we have < amount we need, deincrement n
         if tmp < ra[indr] :
            n-=1
      
      # current minially overlapping recipe as a percentage
      m = np.min(max_overlap)

      n = float(n)/ra.shape[0] #convert to percentage

      # if recipe r overlaps more than minimum overlapping recipe, add r to sugggestion list
      if n > m:
         ind = np.where(max_overlap==m)[0][0]
         max_overlap = np.delete(max_overlap,ind)
         max_overlap = np.append(max_overlap,n)
         max_recipes = np.delete(max_recipes,ind)
         max_recipes = np.append(max_recipes,r)

   #get recipe names
   names = np.asarray([])
   for i in range(max_recipes.size):
      cur.execute("select name from recipes where id = %s" % str(max_recipes[i]))
      try:
         result = cur.fetchone()[0]
      # case where fewer than 5 recipes are suggested
      except:
         result = ' '
      names = np.append(names,result + ' ' + str(max_overlap[i]))

   return np.asarray([names,max_recipes])

def get_notifications(ingredients):
   """
   Compute notifications based on ingredients list.
   ingredients must be formatted as a numpy array:
      ingredients = np.asarray([ing1,ing2,ing3,...])
      where ingi = "Name amt+unit time to expire in days"
   Notifications include:
      item running low
      item about to expire
      item expired
   """
   EXP_DAYS = 5 #number of days til expiration to trigger notification
   ING_LOW = 5 #number of ingredient units to trigger notification
   notifications = np.asarray([])

   # determine notifications for each ingredient
   for ing in ingredients:
      #parse ingredient into name, amount, exp days
      ing_list = ing.split()
      name = " ".join(ing_list[:-4])
      amount = ing_list[-4]
      exp = ing_list[-3]
      
      # ingredient low
      if int(amount) <= ING_LOW:
         msg = name + ";low"
         notifications = np.append(notifications, msg)
      if int(exp) <= EXP_DAYS:
         # ingredient expired
         if int(exp) < 0:
            msg = name + ";expired " + str(-1*int(exp)) + " days ago"
         # ingredient about to expire
         else:
            msg = name + ";expiring in " + exp + " days"
         notifications = np.append(notifications, msg)

   return notifications

if __name__ == "__main__":
      """Driver"""
      # default to home screen
      home_screen()
