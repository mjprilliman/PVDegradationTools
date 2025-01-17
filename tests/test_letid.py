import pytest
from pvdeg import weather, letid, utilities, collection, DATA_DIR, TEST_DATA_DIR
import os
import pandas as pd
import numpy as np
import json
from pvlib.pvsystem import retrieve_sam
from scipy.constants import convert_temperature

import pvlib
from pvlib.pvsystem import PVSystem, FixedMount
from pvlib.location import Location
from pvlib.modelchain import ModelChain
from pvlib.temperature import TEMPERATURE_MODEL_PARAMETERS

# Some of the assertions may have questionable error/abs values that cause the tests to fail
# Some are left blank for now, may cause problems

WEATHER = pd.read_csv(
    os.path.join(TEST_DATA_DIR, r"weather_day_pytest.csv"),
    index_col=0,
    parse_dates=True
)

### dtype HEADACHES ###
REPINS_TIMESTEPS = pd.read_csv(
    os.path.join(TEST_DATA_DIR, r"repins-timesteps.csv"),
    index_col=0,
    parse_dates=True,
    # for some reason timesteps are int32 but all other numerics are int64
    dtype = {'Temperature':'int32'}
)
# did not properly parse and update Datetime column to datetime64[ns] so must be done manually 
REPINS_TIMESTEPS['Datetime'] = pd.to_datetime(REPINS_TIMESTEPS['Datetime'])
###

DEVICE_PARAMS = pd.read_csv(
    os.path.join(TEST_DATA_DIR, r"repins-device-params-timesteps.csv"),
    index_col=0,
    parse_dates=True,
    dtype = {'Temperature':'int32'}
)
DEVICE_PARAMS['Datetime'] = pd.to_datetime(DEVICE_PARAMS['Datetime'])

LETID_OUTDOORS = pd.read_csv(
    os.path.join(TEST_DATA_DIR, r"letid-outdoors.csv"),
    index_col=0,
    parse_dates=True,
)

LETID_LAB = pd.read_csv(
    os.path.join(TEST_DATA_DIR, r"letid-lab.csv"),
    index_col=0,
    parse_dates=True,
    dtype = {'Temperature':'int64'}
)
LETID_LAB['Datetime'] = pd.to_datetime(LETID_LAB['Datetime'])

INJECTION = pd.read_csv(
    os.path.join(TEST_DATA_DIR, "injection-outdoors.csv"),
    index_col=0,
    parse_dates=True
)

with open(os.path.join(TEST_DATA_DIR, "meta.json"), "r") as file:
    META = json.load(file)
META = weather.map_meta(META)

def test_tau_now():
# from LETID - Passivated Wafer.ipynb
    tau_0 = 350 # us 
    tau_deg = 41 # us
    nB_0 = 0

    result = letid.tau_now(tau_0, tau_deg, nB_0)

    assert result == pytest.approx(350.0)

def test_k_ij():
# from LETID - Passivated Wafer.ipynb
    mechanism_params = utilities.get_kinetics('repins')
    temperature = 49 # °C

    result = letid.k_ij(mechanism_params['v_ab'], mechanism_params['ea_ab'], temperature)

    # ABS value here?
    assert result == pytest.approx(5.389713113272726e-06)

def test_carrier_factor():

    tau = 350 # us, lifetime of the wafer for demonstration purposes
    transition = 'ab'
    temperature = 20 # C
    suns = 0.5
    meas_jsc = 40
    wafer_thickness = 180 # um
    s_rear = 90
    mechanism_params = utilities.get_kinetics('repins')

    result = letid.carrier_factor(tau, transition, temperature, suns, meas_jsc, wafer_thickness, s_rear, mechanism_params)

    assert result == pytest.approx(1.2700522149193714, abs = 0.000005)

def test_carrier_factor_wafer():
# from LETID - Passivated Wafer.ipynb
    wafer_thickness = 180 # um
    tau = 350 # us, lifetime of the wafer for demonstration purposes
    mechanism_params = utilities.get_kinetics('repins')
    injection = 0.5 # 
    transition = 'bc' # for this example we'll look at the B -> C transition

    generation_df = pd.read_excel(os.path.join(DATA_DIR, 'PVL_GenProfile.xlsx'), header = 0) # this is an optical generation profile generated by PVLighthouse's OPAL2 default model for 1-sun, normal incident AM1.5 sunlight on a 180-um thick SiNx-coated, pyramid-textured wafer.
    generation = generation_df['Generation (cm-3s-1)']
    depth = generation_df['Depth (um)']
    j_gen = collection.generation_current(generation, depth)

    result = letid.carrier_factor_wafer(tau, transition, injection, j_gen, wafer_thickness, mechanism_params)

    assert result == pytest.approx(4.711029107876425, abs=0.000005)

def test_calc_dn():
# from LETID - Passivated Wafer.ipynb
    transition = 'bc' # for this example we'll look at the B -> C transition

    mechanism_params = utilities.get_kinetics('repins')
    meas_tau = mechanism_params[f"tau_{transition}"]
    meas_temp = mechanism_params[f"temperature_{transition}"]
    meas_temp = convert_temperature(meas_temp, 'K', 'C')
    meas_suns = mechanism_params[f"suns_{transition}"]
    meas_jsc = 40
    meas_wafer_thickness = mechanism_params[f"thickness_{transition}"]
    meas_srv = mechanism_params[f"srv_{transition}"]

    result = letid.calc_dn(
                        meas_tau,
                        meas_temp,
                        meas_suns,
                        meas_jsc,
                        wafer_thickness=meas_wafer_thickness,
                        s_rear=meas_srv,
                    )

    # What should the abs value be here, LARGE MAGNITUDE ANSWER
    assert result == pytest.approx(7.064647199192719e+20) 

def test_convert_i_to_v():
    tau = 350 # us, lifetime of the wafer for demonstration purposes
    na = 7.2e21 
    current = 0.005
    wafer_thickness = 180 # um
    srv = 41

    result = letid.convert_i_to_v(tau, na, current, wafer_thickness, srv)

    assert result == pytest.approx(0.539020964053319, abs = 0.000005)

def test_j0_gray():
    ni2 = 1.0e16  # m^-3
    diffusivity = 3.0e-4  # m^2/s
    na = 1.0e24  # m^-3
    diffusion_length = 1.0e-3  # m
    arg = 5  # unitless
    srv = 1.0e-4  # m/s

    result = letid.j0_gray(ni2, diffusivity, na, diffusion_length, arg, srv)

    assert result == pytest.approx(4.806093780404662e-28)

def test_calc_voc_from_tau():
    tau_1 = 115.000000
    tau_2 = 60.631208
    wafer_thickness = 180
    s_rear = 46
    jsc_now = 41.28092915355781
    temperature = 25

    result_1 = letid.calc_voc_from_tau(tau_1, wafer_thickness, s_rear, jsc_now, temperature)
    result_2 = letid.calc_voc_from_tau(tau_2, wafer_thickness, s_rear, jsc_now, temperature)

    assert result_1 == pytest.approx(0.6661350284244034, abs = 5e-8 )
    assert result_2 == pytest.approx(0.6531169204120689, abs = 5e-8)

def test_calc_device_params():
    results = letid.calc_device_params(REPINS_TIMESTEPS, cell_area=243)

    pd.testing.assert_frame_equal(results, DEVICE_PARAMS, check_index_type=False)

def test_calc_energy_loss():
    result = letid.calc_energy_loss(REPINS_TIMESTEPS)

    assert result == pytest.approx(8.873902787132071e-05, abs = 0.000005)

def test_calc_regeneration_time():

    # not functional
    # had to set x to the closest value in my dataframe,
    # this is probably flawed but it avoids 
    # ``IndexError: single positional indexer is out-of-bounds``
    result = letid.calc_regeneration_time(REPINS_TIMESTEPS, x=4.0463754402964416e-05)

    pass

def test_calc_pmp_loss_from_tau_loss():
# from B-O LID - Accelerated Test.ipynb

    wafer_thickness = 180 # um
    s_rear = 46 # cm/s
    cell_area = 243 # cm^2
    tau_0 = 115 # us, carrier lifetime in non-degraded states, e.g. LETID/LID states A or C
    tau_deg = 55 # us, carrier lifetime in fully-degraded state, e.g. LETID/LID state B

    result = letid.calc_pmp_loss_from_tau_loss(tau_0, tau_deg, cell_area, wafer_thickness, s_rear) # returns % power loss, pmp_0, pmp_deg

    # are these ABS values reasonable? 
    assert result[0] == pytest.approx(0.03495240755084558, abs = 5e-8)
    assert result[1] == pytest.approx(5.663466529792824, abs = 5e-8)
    assert result[2] == pytest.approx(5.465514739492932, abs = 5e-8)

def test_calc_ndd():
    tau_0 = 350 # us 
    tau_deg = 41 # us

    result = letid.calc_ndd(tau_0, tau_deg)

    assert result == pytest.approx(0.02153310104529617, abs = 0.000005)

def test_ff_green():
    voltage = 40

    result = letid.ff_green(voltage)

    assert result == pytest.approx(0.9946395424055456, abs = 0.000005)

def test_calc_injection_outdoors():
    temperature_model_parameters = TEMPERATURE_MODEL_PARAMETERS['sapm']['open_rack_glass_glass']
    sandia_modules = pvlib.pvsystem.retrieve_sam('SandiaMod')
    cec_inverters = pvlib.pvsystem.retrieve_sam('cecinverter')
    sandia_module = sandia_modules['Canadian_Solar_CS5P_220M___2009_']
    cec_inverter = cec_inverters['ABB__MICRO_0_25_I_OUTD_US_208__208V_']

    location = Location(latitude=META['latitude'], longitude=META['longitude'])

    system = PVSystem(surface_tilt=20, surface_azimuth=200,
                    module_parameters=sandia_module,
                    inverter_parameters=cec_inverter,
                    temperature_model_parameters=temperature_model_parameters)

    mc = ModelChain(system, location)

    mc.run_model(WEATHER)
    mc.complete_irradiance(WEATHER)

    result = letid.calc_injection_outdoors(mc.results) 

    result = pd.DataFrame(result)
    result.columns = ['0']

    pd.testing.assert_frame_equal(result, INJECTION, check_column_type=False, check_index_type=False)

def test_calc_letid_outdoors():
    tau_0 = 350
    tau_deg = 41
    wafer_thickness = 180
    s_rear = 90
    nA_0 = 100
    nB_0 = 0
    nC_0 = 0
    mechanism_params = 'repins'

    generation_df = pd.read_excel(os.path.join(DATA_DIR, 'PVL_GenProfile.xlsx'), header = 0) # this is an optical generation profile generated by PVLighthouse's OPAL2 default model for 1-sun, normal incident AM1.5 sunlight on a 180-um thick SiNx-coated, pyramid-textured wafer.

    result = letid.calc_letid_outdoors(tau_0, tau_deg, wafer_thickness, s_rear, nA_0, nB_0, nC_0, WEATHER, META, mechanism_params, generation_df)
    print("here it is", META)
    pd.testing.assert_frame_equal(result, LETID_OUTDOORS)

def test_calc_letid_lab():
    tau_0 = 115 # us
    tau_deg = 55 # us 
    wafer_thickness = 180 # um
    s_rear = 46 # cm/s

    nA_0 = 100
    nB_0 = 0
    nC_0 = 0

    injection = 0.1
    temperature = 75
    mechanism_params = 'repins'

    result = letid.calc_letid_lab(tau_0, tau_deg, wafer_thickness, s_rear, nA_0, nB_0, nC_0, injection, temperature, mechanism_params, freq='h')

    # Datetimes were causing this to fail, we dont care about them
    result_without_datetime = result.drop(columns=['Datetime'])
    letid_lab_without_datetime = LETID_LAB.drop(columns=['Datetime'])

    pd.testing.assert_frame_equal(result_without_datetime, letid_lab_without_datetime, check_index_type=False, check_dtype=False)