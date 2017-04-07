# -*- coding: utf-8 -*-
"""
assemutil.py
------------

Functions to assemble the system of equations for the Finite Element
Analysis.

"""
from __future__ import division, print_function
import numpy as np
from scipy.sparse import coo_matrix
import uelutil as ue
import femutil as fem


def eqcounter(nn, nodes):
    """Counts active equations and creates BCs array IBC

    Parameters
    ----------
    nn : int
      Number of nodes.
    nodes : ndarray
      Array with nodes coordinates and boundary conditions.

    Returns
    -------
    neq : int
      Number of equations in the system after removing the nodes
      with imposed displacements.
    IBC : ndarray (int)
      Array that maps the nodes with number of equations.

    """
    IBC = np.zeros([nn, 2], dtype=np.integer)
    for i in range(nn):
        for k in range(2):
            IBC[i , k] = int(nodes[i , k+3])
    neq = 0
    for i in range(nn):
        for j in range(2):
            if IBC[i, j] == 0:
                IBC[i, j] = neq
                neq = neq + 1

    return neq, IBC


def DME(nn , ne , nodes , elements):
    """Counts active equations, creates BCs array IBC[]
    and the assembly operator DME[]

    Parameters
    ----------
    nn : int
      Number of nodes.
    ne : int
      Number of elements.
    nodes    : ndarray.
      Array with the nodal numbers and coordinates.
    elements : ndarray
      Array with the number for the nodes in each element.

    Returns
    -------
    DME : ndarray (int)
      Assembly operator.
    IBC : ndarray (int)
      Boundary conditions array.
    neq : int
      Number of active equations in the system.

    """
    IELCON = np.zeros([ne, 9], dtype=np.integer)
    DME = np.zeros([ne, 18], dtype=np.integer)

    neq, IBC = eqcounter(nn, nodes)

    for i in range(ne):
        iet = elements[i, 1]
        ndof, nnodes, ngpts = fem.eletype(iet)
        for j in range(nnodes):
            IELCON[i, j] = elements[i, j+3]
            kk = IELCON[i, j]
            for l in range(2):
                DME[i, 2*j+l] = IBC[kk, l]

    return DME , IBC , neq


def retriever(elements , mats , nodes , i):
    """Computes the elemental stiffness matrix of element i

    Parameters
    ----------
    elements : ndarray
      Array with the number for the nodes in each element.
    mats    : ndarray.
      Array with the material profiles.
    nodes    : ndarray.
      Array with the nodal numbers and coordinates.
    i    : int.
      Identifier of the element to be assembled.

    Returns
    -------
    kloc : ndarray (float)
      Array with the local stiffness matrix.
    ndof : int.
      Number of degrees of fredom of the current element.
    """
    IELCON = np.zeros([9], dtype=np.integer)
    iet = elements[i , 1]
    ndof, nnodes, ngpts = fem.eletype(iet)
    elcoor = np.zeros([nnodes, 2])
    im = np.int(elements[i, 2])
    par0 , par1 = mats[im, :]
    for j in range(nnodes):
        IELCON[j] = elements[i, j+3]
        elcoor[j, 0] = nodes[IELCON[j], 1]
        elcoor[j, 1] = nodes[IELCON[j], 2]
    if iet == 1:
        kloc = ue.uel4nquad(elcoor, par1 , par0)
    elif iet == 2:
        kloc = ue.uel6ntrian(elcoor, par1 , par0)
    elif iet == 3:
        kloc = ue.uel3ntrian(elcoor, par1 , par0)
    elif iet == 5:
        kloc = ue.uelspring(elcoor, par1 , par0)
    elif iet == 6:
        kloc =ue.ueltruss2D(elcoor, par1 , par0)
    elif iet == 7:
        kloc = ue.uelbeam2DU(elcoor, par1 , par0)
    
    return kloc , ndof , iet


def assembler(elements, mats, nodes, neq, DME, sparse=True):
    """Assembles the global stiffness matrix

    Parameters
    ----------
    elements : ndarray (int)
      Array with the number for the nodes in each element.
    mats    : ndarray (float)
      Array with the material profiles.
    nodes    : ndarray (float)
      Array with the nodal numbers and coordinates.
    DME  : ndarray (int)
      Assembly operator.
    neq : int
      Number of active equations in the system.
    sparse : boolean (optional)
      Boolean variable to pick sparse assembler. It is True
      by default.

    Returns
    -------
    KG : ndarray (float)
      Array with the global stiffness matrix. It might be
      dense or sparse, depending on the value of _sparse_

    """
    if sparse:
        KG = sparse_assem(elements, mats, nodes, neq, DME)
    else:
        KG = dense_assem(elements, mats, nodes, neq, DME)

    return KG


def dense_assem(elements, mats, nodes, neq, DME):
    """
    Assembles the global stiffness matrix _KG_
    using a dense storing scheme

    Parameters
    ----------
    elements : ndarray (int)
      Array with the number for the nodes in each element.
    mats    : ndarray (float)
      Array with the material profiles.
    nodes    : ndarray (float)
      Array with the nodal numbers and coordinates.
    DME  : ndarray (int)
      Assembly operator.
    neq : int
      Number of active equations in the system.

    Returns
    -------
    KG : ndarray (float)
      Array with the global stiffness matrix in a dense numpy
      array.

    """
    KG = np.zeros((neq, neq))
    nels = elements.shape[0]
    for el in range(nels):
        kloc , ndof , iet  = retriever(elements , mats  , nodes , el)
        if iet == 6:
            dme    = np.zeros([ndof], dtype=np.integer)
            dme[0] = DME[el, 0]
            dme[1] = DME[el, 1]
            dme[2] = DME[el, 3]
            dme[3] = DME[el, 4]
        else:
            dme = DME[el, :ndof]

        for row in range(ndof):
            glob_row = dme[row]
            if glob_row != -1:
                for col in range(ndof):
                    glob_col = dme[col]
                    if glob_col != -1:
                        KG[glob_row, glob_col] = KG[glob_row, glob_col] +\
                                                 kloc[row, col]

    return KG


def sparse_assem(elements, mats, nodes, neq, DME):
    """
    Assembles the global stiffness matrix _KG_
    using a sparse storing scheme

    The scheme used to assemble is COOrdinate list (COO), and
    it converted to Compressed Sparse Row (CSR) afterward
    for the solution phase [1]_.

    Parameters
    ----------
    elements : ndarray (int)
      Array with the number for the nodes in each element.
    mats    : ndarray (float)
      Array with the material profiles.
    nodes    : ndarray (float)
      Array with the nodal numbers and coordinates.
    DME  : ndarray (int)
      Assembly operator.
    neq : int
      Number of active equations in the system.

    Returns
    -------
    KG : ndarray (float)
      Array with the global stiffness matrix in a sparse
      Compressed Sparse Row (CSR) format.

    References
    ----------
    .. [1] Sparse matrix. (2017, March 8). In Wikipedia,
        The Free Encyclopedia.
        https://en.wikipedia.org/wiki/Sparse_matrix

    """
    rows = []
    cols = []
    vals = []
    nels = elements.shape[0]
    for el in range(nels):
        kloc , ndof , iet  = retriever(elements , mats  , nodes , el)
        if iet == 6:
            dme    = np.zeros([ndof], dtype=np.integer)
            dme[0] = DME[el, 0]
            dme[1] = DME[el, 1]
            dme[2] = DME[el, 3]
            dme[3] = DME[el, 4]
        else:
            dme = DME[el, :ndof]
    
        for row in range(ndof):
            glob_row = dme[row]
            if glob_row != -1:
                for col in range(ndof):
                    glob_col = dme[col]
                    if glob_col != -1:
                        rows.append(glob_row)
                        cols.append(glob_col)
                        vals.append(kloc[row, col])

    return coo_matrix((vals, (rows, cols)), shape=(neq, neq)).tocsr()


def loadasem(loads, IBC, neq, nl):
    """Assembles the global Right Hand Side Vector RHSG

    Parameters
    ----------
    loads : ndarray
      Array with the loads imposed in the system.
    IBC : ndarray (int)
      Array that maps the nodes with number of equations.
    neq : int
      Number of equations in the system after removing the nodes
      with imposed displacements.
    nl : int
      Number of loads.

    Returns
    -------
    RHSG : ndarray
      Array with the right hand side vector.

    """
    RHSG = np.zeros([neq])
    for i in range(nl):
        il = int(loads[i, 0])
        ilx = IBC[il, 0]
        ily = IBC[il, 1]
        if ilx != -1:
            RHSG[ilx] = loads[i, 1]
        if ily != -1:
            RHSG[ily] = loads[i, 2]

    return RHSG
