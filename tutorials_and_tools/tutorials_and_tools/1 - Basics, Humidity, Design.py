#!/usr/bin/env python
# coding: utf-8

# # 1 - Basics, Humidity, Design
# ### Module Humidity and Edge Seal Width
# 
# 
# **Requirements:**
# - weather file (psm3 preferred) demo file is provided
# 
# **Objectives:**
# 1. Read in necessary weather data
# 2. Generate solar position, POA, and module temperature
# 3. Generate module humidities
# 4. Calculate edge seal width

# In[1]:


# if running on google colab, uncomment the next line and execute this cell to install the dependencies and prevent "ModuleNotFoundError" in later cells:
# !pip install pvdeg==0.3.1


# In[1]:


import os
import pandas as pd

import pvdeg 
from pvdeg import DATA_DIR


# In[ ]:


# This information helps with debugging and getting support :)
import sys, platform
print("Working on a ", platform.system(), platform.release())
print("Python version ", sys.version)
print("Pandas version ", pd.__version__)
print("pvdeg version ", pvdeg.__version__)


# ## 1. Reading in Weather Data and Site Meta-Data
# Most `pvdeg` functions have been standardized to operate from popular weather files such as TMY3, EPW, and PSM3. For high-performance computer users, NSRDB and other database fetching tools can be used. For these tutorials, we will use local weather files. Unless otherwise stated, functions require the following fields within a weather file:
# 
# - date-time index
# - DNI
# - DHI
# - GHI
# - Temperature, Dry-Bulb
# - Temperature, Dew-Point
# - Wind Speed
# - Relative Humidity
# 
# And the following site-specific metadata. This should be contained in the weather file header.
# 
# - Latitude
# - Longitude
# - Altitude

# In[2]:


PSM_FILE = os.path.join(DATA_DIR,'psm3_demo.csv')

WEATHER, META = pvdeg.weather.read(PSM_FILE,'psm')


# Let's take a closer look at the dataframe (weather) and dictionary (meta) imported above. The structure will be used by most `pvdeg` functions.

# In[3]:


WEATHER.head()


# Meta-Data will vary greatly between weather files. However, at a minimum they should all contain the fields required by `pvdeg` listed above. Let's look at the meta-data generated by our PSM3 weather file. It provides much more information that we need, but at the very end are the three most important fields.

# In[4]:


META


# We'll be working with a lot of time series data, generally with a date-time index. If you're
# processing an entire year of data, you don't need to sort or filter the data. However, you may want
# to filter the data by a few different criteria. Below are some common examples.
# - Filter by date
#     - month
#     - range of months
# - Filter by sun-up hours

# In[5]:


# Let's select the month of June
june_weather = WEATHER[ WEATHER.index.month == 6 ]
june_weather


# In[6]:


# Let's filter the summer months for the northern hemisphere
summer_months = [6,7,8,9]
summer_weather = WEATHER[ WEATHER.index.month.isin( summer_months ) ]
summer_weather


# In[7]:


# lets just select hours from the year where the sun is above the horizon
sunup_weather = WEATHER[ WEATHER['ghi'] > 0 ]
sunup_weather


# ## 2. Solar Position, POA, and Module Temperature
# 
# Many operations with `PVDEG` require solar position, POA irradiance, and module temperature. Usually a `pvdeg` method will calculate these data sets automatically when it is required, however it will not keep the data for external use. For now, we will calculate them directly. This is helpful when you need to use the data for an external calculation. Here, we generate the solar position (azimuth, elevation, etc), plane of array irradiance (POA), and module temperature. `PVDEG` has wrappers for quickly using `PVLIB` to generate these figures with minimal input

# In[8]:


sol_pos = pvdeg.spectral.solar_position(weather_df=WEATHER, meta=META)

poa_df = pvdeg.spectral.poa_irradiance(weather_df=WEATHER, meta=META)#, solar_position=sol_pos)

temp_mod = pvdeg.temperature.module(weather_df=WEATHER, meta=META)#, poa=poa_df)


# For more advanced usage of these functions, refer to the documentation for `pvdeg` and `pvlib`.
# 
# Lets inspect the output from each of these functions
# 
# `solar_position` returns a datetime-indexed dataframe of solar position for the length and frequency given by the weather file.
# 

# In[9]:


sol_pos


# `poa_irradiance` returns a datetime-indexed dataframe as well. Each column contains either the global plane of array irradiance or a particular contribition. Lets look at a time in the index we expect to have daylight.

# In[10]:


poa_df.loc['1999-01-01 13:30:00-07:00':'1999-01-01 17:30:00-07:00']


# `temperature.module` has several optional parameters. Below is an example which explicity uses all of the default values. This function will return a datetime-indexed series matching the index of the given weather file. For more options, see the pvlib documentation for temperature models.
# 
# https://pvlib-python.readthedocs.io/en/stable/reference/pv_modeling/temperature.html
# 
# The optional arguments are:
# - poa : manually enter the POA Irradiance
# - temp_model : choose a PVLIB compatible temperature model
# - conf : choose a recognized module configuration
# - wind_speed_factor : change the empirical wind speed fit paramter

# In[11]:


temp_mod = pvdeg.temperature.module(weather_df = WEATHER, meta = META,
                                    poa = poa_df,
                                    temp_model = 'sapm',
                                    conf= 'open_rack_glass_polymer',
                                    wind_speed_factor = 1)

temp_mod.loc['1999-01-01 13:30:00-07:00':'1999-01-01 17:30:00-07:00']


# ## 3. Module Humidities
# `PVDEG` can be used to calculate the relative humidity of several layers within a PV module: the outside surface of the module, front ecapsulant, back encapsulant, and backsheet. This can be done with 2 techniques: Automatically and Manually.    

# ### 3.a. Automatic
# Use the function `humidity.module`. This method does all of the calculations behind the scenes. It requires only 2 inputs (weather data and meta data). It will return a dataframe with all the layers of the module.

# In[12]:


rh_module = pvdeg.humidity.module(weather_df=WEATHER, meta=META)
rh_module.head()


# ### 3.b. Manual
# Use the individual functions to calculate the RH in each layer. These are named and require more extensive input parameters. This must be done in the correct order:
# 1. Surface Outside
# 2. Front Encapsulant
# 2. Back Encapsulant
# 3. Backsheet

# In[13]:


rh_surface_outside = pvdeg.humidity.surface_outside(rh_ambient=WEATHER['relative_humidity'],
                                                       temp_ambient=WEATHER['temp_air'],
                                                       temp_module=temp_mod)

rh_front_encap = pvdeg.humidity.front_encap(rh_ambient=rh_surface_outside,
                                               temp_ambient=WEATHER['temp_air'],
                                               temp_module=temp_mod)

rh_back_encap = pvdeg.humidity.back_encap(rh_ambient=rh_surface_outside,
                                             temp_ambient=WEATHER['temp_air'],
                                             temp_module=temp_mod)

rh_backsheet = pvdeg.humidity.backsheet_from_encap(rh_back_encap=rh_back_encap,
                                                      rh_surface_outside=WEATHER['relative_humidity'])


# ## 4. Design: Edge Seal Width
# `pvdeg.design.edge_seal_width` calculates the width [cm] required for several years of water ingress. If you do not specify the number of years, it will use the default value of 25. As with most `pvdeg` functions, we can automatically generate all necessary data if we pass the two arguments (weather_df, meta).

# In[14]:


edge_seal_width = pvdeg.design.edge_seal_width(weather_df=WEATHER, meta=META)
edge_seal_width


# Lets look at the calculation step by step. To get the estimated edge seal width, we need the following:
# 1. Humidity Saturation Point
# 2. Edge seal ingress rate ( k ) or the estimated rate of water ingress through edge seal in [cm/hour^0.5]

# In[15]:


psat, psat_avg = pvdeg.humidity.psat(WEATHER['temp_air'])

k = pvdeg.design.edge_seal_ingress_rate(avg_psat=psat_avg)

edge_seal_width = pvdeg.design.edge_seal_width(weather_df=WEATHER, meta=META,
                                               k=k, years=25)

print(edge_seal_width)


# ### Alternate Edge Seal Width
# If you have the dew point, or wet-bulb temperature, you can calculate the edge seal width directly.

# In[17]:


edge_seal_width = pvdeg.design.edge_seal_width(weather_df=WEATHER, meta=META, from_dew_point=True)
edge_seal_width

