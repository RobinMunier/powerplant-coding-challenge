#!/usr/bin/env python
# coding: utf-8


# #Code used to write the requirements.txt file.

# file = open("requirements.txt","w")

# dependencies = ["flask==2.0.2\n", "flask_restful\n", "pandas==1.3.4\n", "numpy==1.21.4\n"]

# file.writelines(dependencies)
# file.close()


# Install the requirements

get_ipython().system('pip install -r requirements.txt')


# Import modules

from flask import Flask
from flask_restful import Resource, Api, reqparse
import json
import pandas as pd
import numpy as np
from itertools import combinations


# Creation of some useful functions

def preprocessing(data):

  """ Function to extract the useful information from the dictionary input file.

  Parameters
  ----------
  data : dict
    Dict containing the data from the input json file.
      
  Returns
  -------
  powerplants : DataFrame
    A DataFrame whose each row represents a powerplant and the columns gather the useful information about it (pmin, pmax, etc.).
  groups : DataFrame
    A DataFrame whose each row represents a group of "mergeable" powerplants and the columns gather the useful information about it (pmin, pmax, etc.). Using these groups allows to decrease the computing time of the whole algorithm when the number of powerplants is large.
  load : float or int
    The load extracted from the data dictionary.        
    
  """

  def make_groups(groups):
        
    """ Function to extract the useful information from the dictionary input file.

    Parameters
    ----------
    groups : DataFrame
      A DataFrame whose each row represents a powerplant and the columns gather the useful information about it (pmin, pmax, etc.).

    Returns
    -------
    groups : DataFrame
      A DataFrame whose each row represents a group of "mergeable" powerplants and the columns gather the useful information about it (pmin, pmax, etc.). Using these groups allows to decrease the computing time of the whole algorithm when the number of powerplants is large.      

    """
    groups['pmin_list']=groups['pmin'].apply(lambda x:[(x,x)])
    for price in groups['price'].unique():
      subgroup = groups.loc[groups['price']==price,:].sort_values(by='pmin', ascending=True).reset_index()
      n_index = len(subgroup.index)
      comb = list(combinations(subgroup.index, 2))
      idx=0
      pmin_list=[]
      if n_index==1:  
          subgroup['pmin_list']=subgroup['pmin'].apply(lambda x:[(x,x)])
          subgroup['name']=subgroup['name'].apply(lambda x:[x])
          groups = pd.concat([groups.loc[groups['price']!=price,:], subgroup], axis=0)
      else:
        while (n_index>=2)&(idx<=len(comb)-1):
          units = subgroup.loc[list(comb[idx]),:]
          if (units['pmin'].iloc[1]<=units['pmax'].iloc[0])&((units['pmin'].iloc[0]<=units['p_range'].iloc[1])|(units['pmin'].iloc[1]<=units['p_range'].iloc[0])):
            pmin_list.append((units['pmin'].iloc[0], units['pmin'].iloc[1]))
            units=pd.DataFrame.from_dict({'name':[[units['name'].iloc[0], units['name'].iloc[1]]], 'pmin':[units['pmin'].min()], 'pmax':[units['pmax'].sum()], 
                                          'price':[units['price'].iloc[0]], 'pmin_list':[pmin_list]})
            units['p_range']=units['pmax']-units['pmin']
            subgroup=pd.concat([units, subgroup.loc[subgroup.index.drop(list(comb[idx])),:]], axis=0).sort_values(by='pmin', ascending=True).reset_index(drop=True)
            n_index-=1
            if n_index>=2:
              comb = list(combinations(subgroup.index, 2))
              idx=0
          else:
            idx+=1
        groups = pd.concat([groups.loc[groups['price']!=price,:], subgroup], axis=0)
    return groups.loc[:,['name','pmin','pmax', 'pmin_list','price']]

  load = data["load"]
  fuels = pd.Series(data["fuels"])
  powerplants = pd.DataFrame(data["powerplants"])

  prices = {'gasfired':fuels.loc['gas(euro/MWh)']+0.3*fuels.loc['co2(euro/ton)'], 'turbojet':fuels.loc['kerosine(euro/MWh)'], 'windturbine':0}
  powerplants['fuel_prices'] = powerplants.type.replace(prices)

  powerplants['actual_efficiency'] = powerplants['efficiency']
  wind_idx = powerplants['type']=='windturbine'
  powerplants.loc[wind_idx, 'actual_efficiency'] = fuels.loc['wind(%)']/100
  powerplants.loc[wind_idx, 'pmax'] *= powerplants.loc[wind_idx, 'actual_efficiency']

  floor = lambda x: ((10*x)//1)/10
  ceil = lambda x: ((10*x)//1 + int((10*x)%1>0))/10
  powerplants['pmin'] = powerplants['pmin'].apply(ceil)
  powerplants['pmax'] = powerplants['pmax'].apply(floor)
  powerplants['price'] = (powerplants['fuel_prices']/powerplants['actual_efficiency']).fillna(np.inf)
  powerplants['name']=powerplants['name'].apply(lambda x:[x])
  powerplants = powerplants.sort_values(by=['price','pmin'], ascending=True).reset_index(drop=True)
  powerplants['p_range']=powerplants['pmax']-powerplants['pmin']

  wind_turbines = powerplants.loc[powerplants['type']=='windturbine',:]
  wind_turbines = pd.DataFrame.from_dict({'name':[[wind_turbines['name'].sum()]], 'pmin':[wind_turbines['pmin'].min()], 'pmax':[wind_turbines['pmax'].sum()], 'price':[wind_turbines['price'].min()], 'pmin_list':[[(-1,-1)]]})
  turbojets = powerplants.loc[powerplants['type']=='turbojet',:]
  turbojets = pd.DataFrame.from_dict({'name':[[turbojets['name'].sum()]], 'pmin':[turbojets['pmin'].min()], 'pmax':[turbojets['pmax'].sum()], 'price':[turbojets['price'].min()], 'pmin_list':[[(-1,-1)]]})
  groups = powerplants.loc[~powerplants['type'].isin(['windturbine','turbojet']),['name','pmin','pmax','p_range','price']]
  groups=make_groups(groups)
  
  groups = pd.concat([wind_turbines, turbojets, groups], axis=0).sort_values(by=['price','pmin'], ascending=True).reset_index(drop=True)
  
  return powerplants, groups, load

def get_strategy(groups, load):
  """ Function to compute the best production strategy.

  Parameters
  ----------
  groups : DataFrame
    A DataFrame whose each row represents a group of "mergeable" powerplants and the columns gather the useful information about it (pmin, pmax, etc.).
  load : float or int
    The load extracted from the data dictionary. 
        
  Returns
  -------
  strategy : dict
    Dictionary with two keys ("units" and "p") whose values are lists containing the groups to use for production and the power each one should deliver.
    
  """
  strategy = {'units':[], 'p':[]}
  best_price = np.inf

  for i in groups.index:
    if (groups.loc[i,'pmax'].sum()>load)&(groups.loc[i,'pmin'].sum()<load):
      best_price = groups.loc[i,'price']*load
      strategy['units'].append(i)
      strategy['p'].append(load)
      break

  for r in range(2,len(groups.index)+1):
    for idx in combinations(groups.index, r):
      units = groups.loc[list(idx),:]
      if (load<units['pmin'].sum())|(units['pmax'].sum()<load):
        continue
      idx_pmax=1
      while (load>units['pmax'].iloc[:idx_pmax].sum()+units['pmin'].iloc[idx_pmax:].sum()):
        idx_pmax+=1 

      current_price = (units['pmax'].iloc[:idx_pmax-1]*units['price'].iloc[:idx_pmax-1]).sum() +       ((load-units['pmax'].iloc[:idx_pmax-1].sum()-units['pmin'].iloc[idx_pmax:].sum())*units['price'].iloc[idx_pmax-1]).sum() +       (units['pmin'].iloc[idx_pmax:]*units['price'].iloc[idx_pmax:]).sum()
      
      if current_price<best_price:
        best_price=current_price
        strategy['units'] = idx
        strategy['p'] = list(units['pmax'].iloc[:idx_pmax-1]) + [load-units['pmax'].iloc[:idx_pmax-1].sum()-units['pmin'].iloc[idx_pmax:].sum()] + list(units['pmin'].iloc[idx_pmax:])
      
      if idx_pmax==r:
        break

  return strategy


def share(x, pmin_list, load, powerplants):
  """ Recursive function computing the best strategy to use in terms of units (the units to use for production and the power each one should deliver) 
  from the best strategy defined in terms of groups (the groups to use for production and the power each one should deliver).

  Parameters
  ----------
  x : list
    A list of lists containing the units name constituting a particular group in the order they have been "merged" to create this group.
  pmin_list : list
    A list of lists containing the pmin of the units constituting a particular group in the order they have been "merged" to create this group.
  load : float or int
    The load we want to generate with units from the group related to the x argument. 
  powerplants : DataFrame
    A DataFrame whose each row represents a powerplant and the columns gather the useful information about it (pmin, pmax, etc.).
      ²
  Returns
  -------
  results : dict
    Dictionary whose keys are the name of the units constituting the group and the associated values are the power these units should deliver in order to optimally
    generate the input load. 
      
  """
  results={}
  if len(x)==1:
    results[x[0][0]]=load
    return results
  else:
    name1 = x[0]
    name2 = x[1]
    pmin1 = pmin_list[-1][0]
    if load<powerplants.loc[powerplants['name'].apply(str)==str(name2), 'pmin'].iloc[0]:
      results = share(name1, pmin_list[:-1], load, powerplants)
    elif (powerplants.loc[powerplants['name'].apply(str)==str(name2), 'pmin'].iloc[0]<=load)&(load<pmin1+powerplants.loc[powerplants['name'].apply(str)==str(name2), 'pmin'].iloc[0]):
      if (pmin1<=powerplants.loc[powerplants['name'].apply(str)==str(name2), 'p_range'].iloc[0]):
        results[name2[0]]=load
      else:
        results = share(name1, pmin_list[:-1], load, powerplants)
    elif (pmin1+powerplants.loc[powerplants['name'].apply(str)==str(name2), 'pmin'].iloc[0]<=load)&(load<=pmin1+powerplants.loc[powerplants['name'].apply(str)==str(name2), 'pmax'].iloc[0]):
      results = share(name1, pmin_list[:-1], pmin1, powerplants)
      results[name2[0]]=load-pmin1
    else:
      results = share(name1, pmin_list[:-1], load-powerplants.loc[powerplants['name'].apply(str)==str(name2), 'pmax'].iloc[0], powerplants)
      results[name2[0]]=powerplants.loc[powerplants['name'].apply(str)==str(name2), 'pmax'].iloc[0]
  return results

def get_results(strategy, groups, powerplants, share=share):
  """ Function to write the results of the optimization of the strategy in a dictionary, in the format required by the rules of the challenge.
 
  Parameters
  ----------
  strategy : dict
    Dictionary with two keys ("units" and "p") whose values are lists containing the groups to use for production and the power each one should deliver.
  groups : DataFrame
    A DataFrame whose each row represents a group of "mergeable" powerplants and the columns gather the useful information about it (pmin, pmax, etc.).
  powerplants : DataFrame
    A DataFrame whose each row represents a powerplant and the columns gather the useful information about it (pmin, pmax, etc.).
  share : func
    Function computing the best strategy to use in terms of units (the units to use for production and the power each one should deliver) 
    from the best strategy defined in terms of groups (the groups to use for production and the power each one should deliver).
       
  Returns
  -------
  results : dict
    Dictionary with two keys ("units" and "p") whose values are lists containing the units and the power each one should deliver.    
  
  """
  results = []
  for (p,unit) in zip(strategy['p'], strategy['units']):
    if unit in groups.loc[groups['pmin_list'].apply(lambda x:x[-1][0]==-1),:].index: # handle the groups of wind powerplants and turbojet powerplants
      for name in groups.loc[unit,'name'][0]:
        commitment=round(min(p, powerplants.loc[powerplants['name'].apply(lambda x:x[0]==name), 'pmax'].iloc[0]),1)
        results.append({"name":name, "p":str(round(min(p, commitment),1))})
        p-=commitment
        if p==0:
          break
    else:
      group_results = share(groups.loc[unit, 'name'], groups.loc[unit, 'pmin_list'], p, powerplants)
      for item in group_results.items():
        results.append({"name":str(item[0]), "p":str(item[1])})
  for name in powerplants.name.apply(lambda x:x[0]):
    if name not in [result['name'] for result in results]:
      results.append({"name":name, "p":str(0)})
  return results


def plan(data):
  """ Function to compute and write in a dictionary the optimal production plan associated to a dictionary input in the same format as the input files provided for 
  the challenge.
    
  Parameters
  ----------
  data : dict
    Dict containing the data from the input json file.
    
  Returns
  -------
  results : dict
    Dictionary with two keys ("units" and "p") whose values are lists containing the units and the power each one should deliver.    
    
  """
  powerplants, groups, load = preprocessing(data)
  strategy = get_strategy(groups, load)
  results = get_results(strategy, groups, powerplants, share)
  return results, len(strategy['units'])>0



# Initialization of the API

app = Flask(__name__)
api = Api(app)


# Creation of a ProductionPlan class. 
# - We pass _Resource_ in the the class definition so that Flask know that this class is an endpoint for our API.
# - We include our POST method inside the class.
# - We link our ProductionPlan class with the /productionplan endpoint using api.add_resource.

class ProductionPlan(Resource): # pass Resource
    def post(self): # define our post method
        parser = reqparse.RequestParser()
        parser.add_argument('name', required=True)
        args = parser.parse_args()
        
        # read the json
        data = json.load(open('{}.json'.format(args['name'])))
        
        # management of errors
        if data['load']!=round(data['load'],1):
            return {
                'ValueError': "load is not a multiple of 0.1 MW"
            }, 500
        elif data['load']<0:
            return {
                'ValueError': "load is negative"
            }, 500
        for fuels in data['fuels'].items():
            if fuels[1]<0:
                return {
                    'ValueError': "the input price of {} is negative".format(fuels[0])
                }, 500
            if ('%' in fuels[0])&(100<fuels[1]):
                return {
                    'ValueError': "the {} is superior to 100%".format(fuels[0])
                }, 500
        for powerplant in data['powerplants']:
            if powerplant['pmin']<0:
                return {
                    'ValueError': "the pmin of {} is negative".format(powerplant['name'])
                }, 500
            if powerplant['pmax']<0:
                return {
                    'ValueError': "the pmax of {} is negative".format(powerplant['name'])
                }, 500
            if (powerplant['efficiency']<0)|(1<powerplant['efficiency']):
                return {
                    'ValueError': "the efficiency of {} does not belong to [0;1]".format(powerplant['name'])
                }, 500
        
        results, solution=plan(data)
        
        if not solution:
                return {
                    'ValueError': "the load cannot be matched by any strategy with the available powerplants"
                }, 500
        
        json.dump(results, open('response_'+args['name'], 'w'))
        return results, 200

api.add_resource(ProductionPlan, '/productionplan') # link the class with the endpoint


# Let's run our app.

if __name__ == '__main__':
    app.run(port=8888)  # run our Flask app on port 8888

