"""
Collection of classes and functions to obtain spectral parameters.
"""

import pvlib
import os
import glob
import pandas as pd
from rex import NSRDBX, Outputs

def load(database, id, **kwargs):
    """
    Load weather data directly from  NSRDB or through any other PVLIB i/o 
    tools function

    Parameters:
    -----------
    database : (str)
        'NSRDB' or 'PVGIS'
    id : (int or tuple)
        If NSRDB, id is the gid for the desired location
        If PVGIS, id is a tuple of (latitude, longitude) for the desired location
    **kwargs : 
        Additional keyword arguments to pass to the get_weather function
        (see pvlib.iotools.get_psm3 for PVGIS, and get_NSRDB for NSRDB)

    Returns:
    --------
    weather_df : (pd.DataFrame)
        DataFrame of weather data
    meta : (dict)
        Dictionary of metadata for the weather data
    """
    if type(id) is tuple:
        location = id
        gid = None
        lat = location[0]
        lon = location[1]
    elif type(id) is int:
        gid = id
        location = None
    else:
        raise TypeError(
            'Project points needs to be either location tuple (latitude, longitude), or gid integer.')

    #TODO: decide wether to follow NSRDB or pvlib conventions...
    # e.g. temp_air vs. air_temperature
    if database == 'NSRDB':
        weather_df, meta = get_NSRDB(gid=gid, location=location, **kwargs)
    elif database == 'PSM3':
        weather_df, meta = pvlib.iotools.get_psm3(latitude=lat, longitude=lon, **kwargs)
        meta['elevation'] = meta['altitude']
        weather_df['air_temperature'] = weather_df['temp_air']
    elif database == 'PVGIS':
        weather_df, _, _, meta = pvlib.iotools.get_pvgis_tmy(latitude=lat, longitude=lon, **kwargs)
    elif database == 'EPW':
        weather_df, meta = pvlib.iotools.read_epw(**kwargs)
    elif database == 'TMY3':
        weather_df, meta = pvlib.iotools.read_tmy3(**kwargs)
    elif database == 'h5':
        weather_df, meta = read_h5(gid=gid, **kwargs)
    else:
        raise NameError('Weather database not found.')

    return weather_df, meta


def read_file(file_in, file_type, **_):
    """
    Read a locally stored weather file of any PVLIB compatible type

    #TODO: add error handling
          check file types (anything .csv will cause trouble)

    Parameters:
    -----------
    file_in : (path)
        full file path to the desired weather file
    file_type : (str)
        type of weather file from list below (verified)
        [psm3, tmy3, epw]
    """
    if not file_type:
        file_type = file_in[-4:]
    read_list = [ i for i in dir(pvlib.iotools) if i.startswith('read') ]

    for func in read_list:
        if file_type in func:
            _read_func = getattr(pvlib.iotools,func)

    weather_df, meta = _read_func(file_in)

    if not isinstance(meta, dict):
        meta = meta.to_dict()

    return weather_df, meta


def read_h5(gid, file, attributes=None, **_):
    """
    Read a locally stored h5 weather file that follows NSRDB conventions.
    
    Parameters:
    -----------
    file_path : (str)
        file path and name of h5 file to be read
    gid : (int)
        gid for the desired location
    attributes : (list)
        List of weather attributes to extract from NSRDB

    Returns:
    --------
    weather_df : (pd.DataFrame)
        DataFrame of weather data
    meta : (dict)
        Dictionary of metadata for the weather data
    """

    fp = os.path.join(os.path.dirname(__file__), file)

    with Outputs(fp, mode='r') as f:   
        meta = f.meta.loc[gid]
        index = f.time_index
        dattr = f.attrs

    #TODO: put into utilities
    if attributes == None:
        attributes = list(dattr.keys())
        try:
            attributes.remove('meta')
            attributes.remove('tmy_year_short')
        except ValueError:
            pass

    weather_df = pd.DataFrame(index=index, columns=attributes)
    for dset in attributes:
        with Outputs(fp, mode='r') as f:   
            weather_df[dset] = f[dset, :, gid]

    return weather_df, meta.to_dict()


def get_NSRDB_fnames(satellite, names, NREL_HPC = False, **_):
    """
    Get a list of NSRDB files for a given satellite and year

    Parameters:
    -----------
    satellite : (str)
        'GOES', 'METEOSAT', 'Himawari', 'SUNY', 'CONUS', 'Americas'
    names : (int or str)
        PVLIB naming convention year or 'TMY':
        If int, year of desired data
        If str, 'TMY' or 'TMY3'
    NREL_HPC : (bool)
        If True, use NREL HPC path
        If False, use AWS path

    Returns:
    --------
    nsrdb_fnames : (list)
        List of NSRDB files for a given satellite and year
    hsds : (bool)
        If True, use h5pyd to access NSRDB files
        If False, use h5py to access NSRDB files
    """

    sat_map = {'GOES' : 'full_disc',
               'METEOSAT' : 'meteosat',
               'Himawari' : 'himawari',
               'SUNY' : 'india',
               'CONUS' : 'conus',
               'Americas' : 'current'}

    if NREL_HPC:
        hpc_fp = '/datasets/NSRDB/'
        hsds = False
    else:
        hpc_fp = '/nrel/nsrdb/'
        hsds = True
        
    if type(names) == int:
        nsrdb_fp = os.path.join(hpc_fp, sat_map[satellite], '*_{}.h5'.format(names))
        nsrdb_fnames = glob.glob(nsrdb_fp)
    else:
        nsrdb_fp = os.path.join(hpc_fp, sat_map[satellite], '*_{}*.h5'.format(names.lower()))
        nsrdb_fnames = glob.glob(nsrdb_fp)
        
    if len(nsrdb_fnames) == 0:
        raise FileNotFoundError(
            "Couldn't find NSRDB input files! \nSearched for: '{}'".format(nsrdb_fp))
    
    return nsrdb_fnames, hsds


def get_NSRDB(satellite, names, NREL_HPC, gid=None, location=None, attributes=None, **_):
    """
    Get NSRDB weather data from different satellites and years. 
    Provide either gid or location tuple.

    Parameters:
    -----------
    satellite : (str)
        'GOES', 'METEOSAT', 'Himawari', 'SUNY', 'CONUS', 'Americas'
    names : (int or str)
        If int, year of desired data
        If str, 'TMY' or 'TMY3'
    NREL_HPC : (bool)
        If True, use NREL HPC path
        If False, use AWS path
    gid : (int)
        gid for the desired location
    location : (tuple)
        (latitude, longitude) for the desired location
    attributes : (list)
        List of weather attributes to extract from NSRDB

    Returns:
    --------
    weather_df : (pd.DataFrame)
        DataFrame of weather data
    meta : (dict)
        Dictionary of metadata for the weather data
    """
    nsrdb_fnames, hsds = get_NSRDB_fnames(satellite, names, NREL_HPC)
    
    dattr = {}
    for i, file in enumerate(nsrdb_fnames):
        with NSRDBX(file, hsds=hsds) as f:
            if i == 0:
                if gid == None: #TODO: add exception handling
                    gid = f.lat_lon_gid(location)
                meta = f['meta', gid].iloc[0]
                index = f.time_index
            
            lattr = f.datasets
            for attr in lattr:
                dattr[attr] = file
                
    if attributes == None:
        attributes = list(dattr.keys())
        try:
            attributes.remove('meta')
            attributes.remove('tmy_year_short')
        except ValueError:
            pass
        
    weather_df = pd.DataFrame(index=index, columns=attributes)

    for dset in attributes:
        with NSRDBX(dattr[dset], hsds=hsds) as f:   
            weather_df[dset] = f[dset, :, gid]

    return weather_df, meta.to_dict()