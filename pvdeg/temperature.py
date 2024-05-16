"""
Collection of classes and functions to calculate different temperatures.
"""

import pvlib
import pvdeg
from functools import partial
import inspect

def map_model(temp_model:str, cell_or_mod:str)->callable:
    """
    Utility function to map string to pvlib function.

    References
    ----------
    https://pvlib-python.readthedocs.io/en/stable/reference/pv_modeling/temperature.html
    """
    # sapm_cell_from_module?
    # prillman diverges from others, used for smoothing/interp      

    # double check that models are in correct maps
    module = { # only module
        'sapm' : pvlib.temperature.sapm_module,
    }

    cell = { # only cell 
        'sapm' : pvlib.temperature.sapm_cell,
        'pvsyst' : pvlib.temperature.pvsyst_cell,
        'ross' : pvlib.temperature.ross,
        'noct_sam' : pvlib.temperature.noct_sam,  
        'generic_linear' : pvlib.temperature.generic_linear,
    }

    agnostic = { # module or cell
        'faiman' : pvlib.temperature.faiman,
        'faiman_rad' : pvlib.temperature.faiman_rad,
        'fuentes' : pvlib.temperature.fuentes,
    }

    super_map = {'module' : module, 'cell' : cell}
    agnostic.update(super_map[cell_or_mod]) # bad naming

    return agnostic[temp_model]

def _wind_speed_factor(temp_model:str, meta:dict, wind_factor:float):
    if temp_model == "sapm":
        wind_speed_factor = (10 / float(meta["wind_height"])) ** wind_factor
    elif temp_model == "pvsyst":
        wind_speed_factor = (2 / float(meta["wind_height"])) ** wind_factor
    elif temp_model == "faiman":
        wind_speed_factor = (2 / float(meta["wind_height"])) ** wind_factor
    elif temp_model == "faiman_rad":
        wind_speed_factor = (2 / float(meta["wind_height"])) ** wind_factor
    elif temp_model == "fuentes":
        wind_speed_factor = (5 / float(meta["wind_height"])) ** wind_factor
    elif temp_model == "ross":
        wind_speed_factor = (
            10 / float(meta["wind_height"])
        ) ** wind_factor  # I had to guess what this one was
    elif temp_model == "noct_sam":
        if meta["wind_height"] > 3:
            wind_speed_factor = 2
        else:
            wind_speed_factor = (
                1  # The wind speed height is managed weirdly for this one.
            )
    elif temp_model == "prilliman":
        wind_speed_factor = (
            1  # this model will take the wind speed height in and do an adjustment.
        )
    elif temp_model == "generic_linear":
        wind_speed_factor = (10 / float(meta["wind_height"])) ** wind_factor
    elif temp_model == "GenericLinearModel":
        wind_speed_factor = (2 / float(meta["wind_height"])) ** wind_factor
        # this one does a linear conversion from the other models, faiman, pvsyst, noct_sam, sapm_module and generic_linear.
        # An appropriate facter will need to be figured out.
    else:
        wind_speed_factor = 1  # this is just hear for completeness.

    return wind_speed_factor


def module(
    weather_df,
    meta,
    poa=None,
    conf="open_rack_glass_polymer",
    temp_model = "sapm",
    wind_factor=0.33,
    model_args=None
):
    """
    Calculate module surface temperature using pvlib.

    Parameters
    ----------
    weather_df : (pd.dataframe)
        Data Frame with minimum requirements of 'temp_air' and 'wind_speed'
    meta : (dict)
        Weather meta-data dictionary (location info)
    poa : pandas.DataFrame
         Contains keys/columns 'poa_global', 'poa_direct', 'poa_diffuse',
         'poa_sky_diffuse', 'poa_ground_diffuse'.

    model : pvdeg.scenario.TempModel

    temp_model : str, optional
        The temperature model to use, Sandia Array Performance Model 'sapm'
        from pvlib by default.

    conf : str, optional
        The configuration of the PV module architecture and mounting
        configuration.
        Options:
            'sapm': 'open_rack_glass_polymer' (default),
            'open_rack_glass_glass', 'close_mount_glass_glass',
            'insulated_back_glass_polymer'
    module_kwarg: dict
        Keyword arguments for module parameters. 

    Returns
    -------
    module_temperature : pandas.DataFrame
        The module temperature in degrees Celsius at each time step.
    """
    if temp_model == 'sapm' or temp_model == 'pvsyst':
        parameters = pvlib.temperature.TEMPERATURE_MODEL_PARAMETERS[temp_model][conf]

    if poa is None:
        poa = pvdeg.spectral.poa_irradiance(weather_df, meta)
    if "wind_height" not in meta.keys():
        wind_speed_factor = 1
    else:
        wind_speed_factor = _wind_speed_factor(temp_model, meta, wind_factor)

    # moved outside of conditionals
    poa_global=poa["poa_global"],
    temp_air=weather_df["temp_air"],
    wind_speed=weather_df["wind_speed"] * wind_speed_factor,

    # implementing temperature models    


    func = map_model(temp_model)


    # function may not need all of these parameters, figure out what will be problematic
    for key in model_args.keys():
        func = partial(func, key=model_args[key]) # allowed?

    p_func = partial(func, poa_global=poa_global, temp_air=temp_air, wind_speed=wind_speed)



    # determine issues with kwargs?
    # do they stay in the class or should we pass them in here
    if temp_model == "sapm":
        module_temperature = p_func(
            # add nessecary parameters in here
            a=parameters["a"],
            b=parameters["b"],
        )        

    else:
        # TODO: add options for temperature model
        print("There are other models but they haven't been implemented yet!")
    return module_temperature



def cell(
    weather_df,
    meta,
    poa=None,
    temp_model="sapm",
    conf="open_rack_glass_polymer",
    wind_factor=0.33,
):
    """
    Calculate the PV cell temperature using PVLIB
    Currently this only supports the SAPM temperature model.

    Parameters:
    -----------
    weather_df : (pd.dataframe)
        Data Frame with minimum requirements of 'temp_air' and 'wind_speed'
    meta : (dict)
        Weather meta-data dictionary (location info)
    poa : (dataframe or series, optional)
        Dataframe or series with minimum requirement of 'poa_global'
    temp_model : (str, optional)
        Specify which temperature model from pvlib to use. Current options:
        'sapm'
    conf : (str)
        The configuration of the PV module architecture and mounting
        configuration.
        Options: 'open_rack_glass_polymer' (default), 'open_rack_glass_glass',
                 'close_mount_glass_glass', 'insulated_back_glass_polymer'
    wind_factor : float, optional
        Wind speed correction exponent to account for different wind speed measurement heights
        between weather database (e.g. NSRDB) and the tempeature model (e.g. SAPM)
        The NSRDB provides calculations at 2 m (i.e module height) but SAPM uses a 10 m height.
        It is recommended that a power-law relationship between height and wind speed of 0.33
        be used*. This results in a wind speed that is 1.7 times higher. It is acknowledged that
        this can vary significantly.

    R. Rabbani, M. Zeeshan, "Exploring the suitability of MERRA-2 reanalysis data for wind energy
        estimation, analysis of wind characteristics and energy potential assessment for selected
        sites in Pakistan", Renewable Energy 154 (2020) 1240-1251.

    Return:
    -------
    temp_cell : pandas.DataFrame
        This is the temperature of the cell in a module at every time step.[°C]
    """

    if "wind_height" not in meta.keys():
        wind_speed_factor = 1
    else:
        wind_speed_factor = _wind_speed_factor(temp_model, meta, wind_factor)

    parameters = pvlib.temperature.TEMPERATURE_MODEL_PARAMETERS[temp_model][conf]

    if poa is None:
        poa = pvdeg.spectral.poa_irradiance(weather_df, meta)

    if temp_model == "sapm":
        temp_cell = pvlib.temperature.sapm_cell(
            poa_global=poa["poa_global"],
            temp_air=weather_df["temp_air"],
            wind_speed=weather_df["wind_speed"] * wind_speed_factor,
            **parameters,
        )
    else:
        # TODO: add options for temperature model
        print("There are other models but they haven't been implemented yet!")

    return temp_cell

# move to scenario method?
# no reason we have to be providing a reference to the scenario could swap for weather and meta params
def scenario_temperature(
    scenario = pvdeg.scenario.Scenario,
    poa=None,
    temp_model="sapm",
    conf="open_rack_glass_polymer", # only for sapm and pvsys
    wind_factor=0.33,
    cell_or_mod=None, # 'cell' or 'mod'
    irradince_kwarg=None,
    model_kwarg=None,
    ):

    weather_df = scenario.weather_data
    meta = scenario.meta_data

    if "wind_height" not in meta.keys():
        wind_speed_factor = 1
    else:
        wind_speed_factor = _wind_speed_factor(temp_model, meta, wind_factor)

    if temp_model in ['sapm', 'pvsys']:
        parameters = pvlib.temperature.TEMPERATURE_MODEL_PARAMETERS[temp_model][conf]

    # will break if none in the kwarg
    poa = pvdeg.spectral.poa_irradiance(weather_df, meta, **irradince_kwarg) # seperate kwargs like poa kwargs for angle, tilt, azimuth, model?

    # ALWAYS try to apply all of these to the temp model, 
    # irrelevant key,value pair will be ignored (NO ERROR)
    weather_args = {
    'poa_global' : poa["poa_global"],
    'temp_air' : weather_df["temp_air"],
    'wind_speed' : weather_df["wind_speed"] * wind_speed_factor, # what if we dont always want the wind, can be overwritten by the model_kwarg
    }

    # only apply nessecary values to the model, 
    # gets signature for checks
    func = map_model(temp_model, cell_or_mod)
    sig = inspect.signature(func)

    # unpack signature into list for merging all dictionaries
    model_args = {
        k: (v.default if v.default is not inspect.Parameter.empty else None)
        for k,v in sig.parameters.items()
    }

    # if key is present update the value in the function signature
    for key in model_args:
        # we only want to update the values with matching keys
        if key in model_args:
            model_args[key] = weather_args[key]
   
    # calculated based on material for sapm and pvsys
    if parameters:
        model_args.update(parameters)
    
    # add optional kwargs
    # rename model_args?
    model_args.update(**model_kwarg)
    
    # temp calc using dynamic model
    temperature = func(**model_args)

    return temperature

