######################################################################
# Copyright (C) 2014 Jaakko Luttinen
#
# This file is licensed under Version 3.0 of the GNU General Public
# License. See LICENSE for a text of the license.
######################################################################

######################################################################
# This file is part of BayesPy.
#
# BayesPy is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation.
#
# BayesPy is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with BayesPy.  If not, see <http://www.gnu.org/licenses/>.
######################################################################

"""
Demonstrate switching linear state-space model
"""

import numpy as np
import matplotlib.pyplot as plt

from bayespy.nodes import GaussianARD, \
                          GaussianMarkovChain, \
                          CategoricalMarkovChain, \
                          Dirichlet, \
                          Mixture, \
                          Gamma, \
                          SumMultiply

from bayespy.inference.vmp.vmp import VB
from bayespy.inference.vmp import transformations

import bayespy.plot.plotting as bpplt

def switching_linear_state_space_model(K=3, D=10, N=100, M=20):

    #
    # Linear state-space models
    #

    # Dynamics matrix with ARD
    # (K,1,1,1,D) x ()
    alpha = Gamma(1e-5,
                  1e-5,
                  plates=(K,1,1,1,D),
                  name='alpha')
    # (K,1,1,D) x (D)
    A = GaussianARD(0,
                    alpha,
                    shape=(D,),
                    plates=(K,1,1,D),
                    name='A',
                    plotter=bpplt.GaussianHintonPlotter())
    A.initialize_from_value(np.identity(D)*np.ones((K,1,1,D,D)))

    # Latent states with dynamics
    # (K,1) x (N,D)
    X = GaussianMarkovChain(np.zeros(D),         # mean of x0
                            1e-3*np.identity(D), # prec of x0
                            A,                   # dynamics
                            np.ones(D),          # innovation
                            n=N,                 # time instances
                            name='X',
                            plotter=bpplt.GaussianMarkovChainPlotter())
    X.initialize_from_value(10*np.random.randn(K,1,N,D))

    # Mixing matrix from latent space to observation space using ARD
    # (K,1,1,D) x ()
    gamma = Gamma(1e-5,
                  1e-5,
                  plates=(K,1,1,D),
                  name='gamma')
    # (K,M,1) x (D)
    C = GaussianARD(0,
                    gamma,
                    shape=(D,),
                    plates=(K,M,1),
                    name='C',
                    plotter=bpplt.GaussianHintonPlotter())

    # Underlying noiseless function
    # (K,M,N) x ()
    F = SumMultiply('i,i', 
                    C, 
                    X)
    
    #
    # Switching dynamics (HMM)
    #

    # Prior for initial state probabilities
    rho = Dirichlet(1e-3*np.ones(K),
                    name='rho')

    # Prior for state transition probabilities
    V = Dirichlet(1e-3*np.ones(K),
                  plates=(K,),
                  name='V')
    V.initialize_from_value(1000*np.identity(K) + 1*np.ones((K,K)))

    # Hidden states (with unknown initial state probabilities and state
    # transition probabilities)
    Z = CategoricalMarkovChain(rho, V,
                               states=N,
                               name='Z',
                               plotter=bpplt.CategoricalMarkovChainPlotter())

    #
    # Mixing the models
    #

    # Observation noise
    tau = Gamma(1e-5,
                1e-5,
                name='tau')
    tau.initialize_from_value(1)

    # Emission/observation distribution
    Y = Mixture(Z, GaussianARD, F, tau,
                cluster_plate=-3,
                name='Y')

    Q = VB(Y, 
           Z, rho, V,
           C, gamma, X, A, alpha,
           tau)

    return Q

def run_slssm(y, D, K, seed=42, rotate=True, debug=False, maxiter=100, monitor=False):
    (M, N) = np.shape(y)

    # Construct model
    Q = switching_linear_state_space_model(M=1, K=K, N=N, D=D)

    # Add observations/data
    Q['Y'].observe(y)

    # Set up rotation speed-up
    if rotate:
        # Rotate the D-dimensional state space (X, A, C)
        rotA = transformations.RotateGaussianARD(Q['A'], 
                                                 Q['alpha'])
        rotX = transformations.RotateGaussianMarkovChain(Q['X'], 
                                                         rotA)
        rotC = transformations.RotateGaussianARD(Q['C'],
                                                 Q['gamma'])
        R = transformations.RotationOptimizer(rotX, rotC, D)
        if debug:
            rotate_kwargs = {'maxiter': 10,
                             'check_bound': True,
                             'check_gradient': True}
        else:
            rotate_kwargs = {'maxiter': 10}

    # Run inference
    for n in range(maxiter):
        #Q.update('C', 'Z', 'X', 'A', 'tau', plot=monitor)
        Q.update(plot=monitor)
        R.rotate(**rotate_kwargs)
    

def run(N=1000, maxiter=30, D=2, K=3, seed=42, plot=True, debug=False, monitor=True):

    # Use deterministic random numbers
    if seed is not None:
        np.random.seed(seed)

    #
    # Generate data
    #

    # Two states: 1) oscillation, 2) random walk
    w1 = 0.02 * 2*np.pi
    A = [ [[np.cos(w1), -np.sin(w1)],
           [np.sin(w1), np.cos(w1)]],
          [[1.0, 0.0],
           [0.0, 1.0]] ]
    C = [ [[1.0, 0.0]],
          [[0.5, 0.5]] ]

    # State switching probabilities
    q = 0.98         # probability to stay in the same state
    r = (1-q)/(2-1) # probability to switch
    P = q*np.identity(2) + r*(np.ones((2,2))-np.identity(2))
    
    X = np.zeros((N, 2))
    Z = np.zeros(N)
    Y = np.zeros(N)
    z = np.random.randint(2)
    x = np.random.randn(2)
    Z[0] = z
    X[0,:] = x
    for n in range(1,N):
        x = np.dot(A[z], x) + np.random.randn(2)
        y = np.dot(C[z], x) + np.random.randn()
        z = np.random.choice(2, p=P[z])

        Z[n] = z
        X[n,:] = x
        Y[n] = y

    if plot:
        plt.figure()
        plt.plot(Y)

    #
    # Use switching linear state-space model for inference
    #

    Q = run_slssm(Y[None,:], D, K, 
                  seed=seed, 
                  debug=debug,
                  maxiter=maxiter,
                  monitor=monitor)


    #
    # Show results
    #

    if plot:
        Q.plot()
        
    plt.show()
    

if __name__ == '__main__':
    import sys, getopt, os
    try:
        opts, args = getopt.getopt(sys.argv[1:],
                                   "",
                                   ["n=",
                                    "k=",
                                    "seed=",
                                    "debug",
                                    "maxiter="])
    except getopt.GetoptError:
        print('python demo_lssm.py <options>')
        print('--n=<INT>        Number of data vectors')
        print('--d=<INT>        Latent space dimensionality')
        print('--k=<INT>        Number of mixed models')
        print('--maxiter=<INT>  Maximum number of VB iterations')
        print('--seed=<INT>     Seed (integer) for the random number generator')
        print('--debug          Check that the rotations are implemented correctly')
        sys.exit(2)

    kwargs = {}
    for opt, arg in opts:
        if opt == "--maxiter":
            kwargs["maxiter"] = int(arg)
        elif opt == "--d":
            kwargs["D"] = int(arg)
        elif opt == "--k":
            kwargs["K"] = int(arg)
        elif opt == "--seed":
            kwargs["seed"] = int(arg)
        elif opt == "--debug":
            kwargs["debug"] = True
        elif opt in ("--n",):
            kwargs["N"] = int(arg)
        else:
            raise ValueError("Unhandled option given")

    run(**kwargs)