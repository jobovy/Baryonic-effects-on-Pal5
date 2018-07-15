import glob
import pickle
import numpy as np
from numpy.polynomial import Polynomial
from scipy import ndimage, signal, interpolate, integrate
from galpy.orbit import Orbit
from galpy.potential import MWPotential2014, turn_physical_off, MiyamotoNagaiPotential, plotDensities,evaluateDensities,plotPotentials
from galpy.util import bovy_conversion, save_pickles, bovy_coords, bovy_plot
import pal5_util
import gd1_util
from gd1_util import R0, V0
import custom_stripping_df
import seaborn as sns
import astropy.units as u
from galpy import potential
from matplotlib import cm, pyplot
from galpy.potential import DehnenSmoothWrapperPotential as DehnenWrap

ro=8.
vo=220.

#List of important functions

#compute_Acos_Asin(n=9,l=19,a=1./ro,radial_order=40,costheta_order=40,phi_order=40)

#MWPotentialSCFbar(mbar,Acos,Asin,rs=1.,normalize=False,pat_speed=40.,fin_phi_deg=27.,t_stream_age=5.,t_on=2.,tgrow=2)

#MWPotentialSCFbar_invert(mbar,Acos,Asin,rs=1.,normalize=False,pat_speed=40.,fin_phi_deg=27.,t_stream_age=5.,t_on=2.,tgrow=2)

   

#setup the bar

#compute normalization 
#constants
x0=1.49 # kpc
y0=0.58
z0=0.4
q= 0.6

Mbar=10**10 #Msun, half of what Wang is using, same as Pearson

def tform_from_t_on(t_on=2.,pat_speed=40.,tgrow=2):
        
    omegaP=pat_speed*(ro/vo)    
    Tbar=2.*np.pi/omegaP #bar period in galpy units.
    t_on=t_on/bovy_conversion.time_in_Gyr(vo,ro)
    tsteady=tgrow*Tbar
    tform = t_on + tsteady
    return tform #in galpy units


def rho1(R,z):
    return (2.*np.pi*x0*y0)*R*np.exp(-0.5*(np.sqrt(R**4 + (z/z0)**4)))

rho1norm= integrate.nquad(rho1,[[0,np.inf],[-np.inf,np.inf]])[0]

def rho2(R):
    return (z0**1.85 *4.*np.pi/q**2)*R**(0.15)*np.exp(-R/z0)

rho2norm= integrate.quad(rho2,0,np.inf)[0]
rho0=Mbar/(rho1norm + rho2norm)

def r1c(R,z,p):
    return ((R**4.)*(np.cos(p)**2./x0**2 + np.sin(p)**2/y0**2)**2 + (z/z0)**4.)**(0.25)

def r2c(R,z):
    return np.sqrt((q*R)**2. + z**2.)/z0


def rho_bar_cyl(R,z,p):
    return rho0*(np.exp((-r1c(R,z,p)**2.)/2.) + r2c(R,z)**(-1.85)*np.exp(-r2c(R,z)))


#compute SCF expansion coeffs
def compute_Acos_Asin(n=9,l=19,a=1./ro,radial_order=40,costheta_order=40,phi_order=40):
    
    Acos,Asin= potential.scf_compute_coeffs(lambda R,z,p: rho_bar_cyl(R*8.,z*8.,p)/(10**9.*bovy_conversion.dens_in_msolpc3(220.,8.)),
                                        N=n+1,L=l+1,a=a,radial_order=radial_order,costheta_order=costheta_order,phi_order=phi_order)
                                        
    return (Acos,Asin)
    
    
#setup no grow bar, just for book keeping

def MWPotentialSCFbar_nogrow(mbar,Acos,Asin,rs=1.,normalize=False,pat_speed=40.,fin_phi_deg=27.,t_stream_age=5.):
    
    a=rs/ro
    omegaP=pat_speed*(ro/vo)
    
    fin_phi= np.radians(fin_phi_deg)
    #init_phi= fin_phi - o_p*(tpal5age*Gyr_to_s)
    
    init_phi= fin_phi - omegaP*t_stream_age/bovy_conversion.time_in_Gyr(vo,ro)
    
    mrat=mbar/10.**10. #10^10 mass of bar used to compute Acos and Asin
    
    static_bar=potential.SCFPotential(amp=mrat,Acos=Acos,Asin=Asin,a=a,normalize=normalize)
    
    #Note only m=0 terms are considered 
    static_axi_bar=potential.SCFPotential(amp=mrat,Acos=np.atleast_3d(Acos[:,:,0]),a=a)
    
    barrot=potential.SolidBodyRotationWrapperPotential(pot=static_bar,omega=omegaP,ro=ro,vo=vo,pa=init_phi)
    
    if mbar <= 5.*10**9. :
        MWP2014SCFbar=[MWPotential2014[0],MiyamotoNagaiPotential(amp=(6.8-mrat)*10.**10*u.Msun,a=3./8.,b=0.28/8.),MWPotential2014[2],barrot]
        turn_physical_off(MWP2014SCFbar)
        #setup the corresponding axisymmetric bar
        MWP2014SCFnobar= [MWPotential2014[0],MiyamotoNagaiPotential(amp=(6.8-mrat)*10.**10*u.Msun,a=3./8.,b=0.28/8.),MWPotential2014[2],static_axi_bar]
        turn_physical_off(MWP2014SCFnobar)
        
    else : 
        MWP2014SCFbar=[MiyamotoNagaiPotential(amp=(6.8+0.5-mrat)*10.**10*u.Msun,a=3./8.,b=0.28/8.),MWPotential2014[2],barrot]
        turn_physical_off(MWP2014SCFbar)
        
        MWP2014SCFnobar= [MiyamotoNagaiPotential(amp=(6.8+0.5-mrat)*10.**10*u.Msun,a=3./8.,b=0.28/8.),MWPotential2014[2],static_axi_bar]
        turn_physical_off(MWP2014SCFnobar)
        
    return (MWP2014SCFbar,MWP2014SCFnobar)
    
    

def MWPotentialSCFbar(mbar,Acos,Asin,rs=1.,normalize=False,pat_speed=40.,fin_phi_deg=27.,t_stream_age=5.,t_on=2.,tgrow=2):
    
    '''
    t_stream_age : age of the stream/max stripping time
    t_on: time in Gyr in the past at which the bar acquired full strength
    tgrow: no of bar periods it took the bar to grow to full strength starting at tform
            
    '''
    
    #setup the full strength bar and axisymmetric "bar"
    a=rs/ro
    omegaP=pat_speed*(ro/vo)
    
    fin_phi= np.radians(fin_phi_deg)
        
    init_phi= fin_phi - omegaP*t_stream_age/bovy_conversion.time_in_Gyr(vo,ro)
    
    mrat=mbar/10.**10. #10^10 mass of bar used to compute Acos and Asin
    
    static_bar=potential.SCFPotential(amp=mrat,Acos=Acos,Asin=Asin,a=a,normalize=normalize)
    
    #Note only m=0 terms are considered 
    static_axi_bar=potential.SCFPotential(amp=mrat,Acos=np.atleast_3d(Acos[:,:,0]),a=a)
    
    barrot=potential.SolidBodyRotationWrapperPotential(pot=static_bar,omega=omegaP,ro=ro,vo=vo,pa=init_phi)
    
    if mbar <= 5.*10**9. :
        MWP2014SCFbar=[MWPotential2014[0],MiyamotoNagaiPotential(amp=(6.8-mrat)*10.**10*u.Msun,a=3./8.,b=0.28/8.),MWPotential2014[2],barrot]
        turn_physical_off(MWP2014SCFbar)
        #setup the corresponding axisymmetric bar
        MWP2014SCFnobar= [MWPotential2014[0],MiyamotoNagaiPotential(amp=(6.8-mrat)*10.**10*u.Msun,a=3./8.,b=0.28/8.),MWPotential2014[2],static_axi_bar]
        turn_physical_off(MWP2014SCFnobar)
        
    else : 
        MWP2014SCFbar=[MiyamotoNagaiPotential(amp=(6.8+0.5-mrat)*10.**10*u.Msun,a=3./8.,b=0.28/8.),MWPotential2014[2],barrot]
        turn_physical_off(MWP2014SCFbar)
        
        MWP2014SCFnobar= [MiyamotoNagaiPotential(amp=(6.8+0.5-mrat)*10.**10*u.Msun,a=3./8.,b=0.28/8.),MWPotential2014[2],static_axi_bar]
        turn_physical_off(MWP2014SCFnobar)
        
    
    #setup Dehnen smooth growth wrapper for the bar
    #convert to galpy units
    t_stream_age=t_stream_age/bovy_conversion.time_in_Gyr(vo,ro)
    
    Tbar=2.*np.pi/omegaP #bar period in galpy units.
    t_on=t_on/bovy_conversion.time_in_Gyr(vo,ro)
    tsteady=tgrow*Tbar
    tform = t_on + tsteady

    
    
    #if t_on >= t_pal5_age, then Pal 5 sees the bar as always on
    if t_on >= t_stream_age :
        return (MWP2014SCFbar,MWP2014SCFnobar)
    
    elif tform >= t_stream_age:
        print ("tform > age of Pal 5 stream")
        
    elif tform < t_stream_age :
           
        #change tform in the past, i.e. instead of from today to time in the future from 5 Gyr in the past
        tform=t_stream_age-tform
        MWbar_grow=DehnenWrap(amp=1.,pot=MWP2014SCFbar,tform=tform,tsteady=tsteady)  
        MWaxibar_destroy=DehnenWrap(amp=-1.,pot=MWP2014SCFnobar,tform=tform,tsteady=tsteady) 
       
        growbarpot=[MWbar_grow,MWP2014SCFnobar,MWaxibar_destroy]
        
        turn_physical_off(growbarpot)
    
    return (growbarpot,MWP2014SCFnobar)
    

def MWPotentialSCFbar_invert(mbar,Acos,Asin,rs=1.,normalize=False,pat_speed=40.,fin_phi_deg=27.,t_stream_age=5.,t_on=2.,tgrow=2):
    
    '''
    t_stream_age : age of the stream/max stripping time
    tform: time in Gyr in the past at which the bar started to form
    tgrow: no of bar periods it took the bar to grow to full strength starting at tform
    
        
    '''
    
    #setup the full strength bar and axisymmetric "bar"
    a=rs/ro
    omegaP=pat_speed*(ro/vo)
    
    fin_phi= np.radians(fin_phi_deg)
        
    mrat=mbar/10.**10. #10^10 mass of bar used to compute Acos and Asin
    
    static_bar=potential.SCFPotential(amp=mrat,Acos=Acos,Asin=Asin,a=a,normalize=normalize)
    
    #Note only m=0 terms are considered 
    static_axi_bar=potential.SCFPotential(amp=mrat,Acos=np.atleast_3d(Acos[:,:,0]),a=a)
    
    #pa = final phi and omega is negative since we are going back in time
    barrot=potential.SolidBodyRotationWrapperPotential(pot=static_bar,omega=-omegaP,ro=ro,vo=vo,pa=fin_phi)
    
    if mbar <= 5.*10**9. :
        MWP2014SCFbar=[MWPotential2014[0],MiyamotoNagaiPotential(amp=(6.8-mrat)*10.**10*u.Msun,a=3./8.,b=0.28/8.),MWPotential2014[2],barrot]
        turn_physical_off(MWP2014SCFbar)
        #setup the corresponding axisymmetric bar
        MWP2014SCFnobar= [MWPotential2014[0],MiyamotoNagaiPotential(amp=(6.8-mrat)*10.**10*u.Msun,a=3./8.,b=0.28/8.),MWPotential2014[2],static_axi_bar]
        turn_physical_off(MWP2014SCFnobar)
        
    else : 
        MWP2014SCFbar=[MiyamotoNagaiPotential(amp=(6.8+0.5-mrat)*10.**10*u.Msun,a=3./8.,b=0.28/8.),MWPotential2014[2],barrot]
        turn_physical_off(MWP2014SCFbar)
        
        MWP2014SCFnobar= [MiyamotoNagaiPotential(amp=(6.8+0.5-mrat)*10.**10*u.Msun,a=3./8.,b=0.28/8.),MWPotential2014[2],static_axi_bar]
        turn_physical_off(MWP2014SCFnobar)
        
    
    #setup Dehnen smooth growth wrapper for the bar
    
    #while going back, t_on = tform, then deconstruct the bar to no bar during tsteady
    tform=t_on/bovy_conversion.time_in_Gyr(vo,ro)
    
    Tbar=2.*np.pi/omegaP
    tsteady=tgrow*Tbar
    
    MWaxibar_grow=DehnenWrap(amp=1.,pot=MWP2014SCFnobar,tform=tform,tsteady=tsteady)  
    MWbar_destroy=DehnenWrap(amp=-1.,pot=MWP2014SCFbar,tform=tform,tsteady=tsteady) 
       
    growbarpot_invert=[MWP2014SCFbar,MWaxibar_grow,MWbar_destroy]
    turn_physical_off(growbarpot_invert)
    
    return growbarpot_invert   
    
