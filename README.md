# Powerplant Coding Challenge<br>

by Robin Munier

<hr style="border:2px solid gray">
<br>

This is my solution to the powerplant-coding-challenge proposed by the SPaaS team of ENGIE here : https://github.com/gem-spaas/powerplant-coding-challenge


## Installations

The API has been created with the module _flask_. The modules _flask_ and _flask_restful_ are included in the dependencies installed in the code (the file _powerplant_coding_challenge.py_).

Indeed, the _requirements.txt_ file has been created this way.


```python
# Code used to write the requirements.txt file.

file = open("requirements.txt","w")

dependencies = ["flask==2.0.2\n", "flask_restful\n", "pandas==1.3.4\n", "numpy==1.21.4\n"]

file.writelines(dependencies)
file.close()
```

The _powerplant_coding_challenge.py_ code includes the following line which install the needed dependencies :

```python
get_ipython().system('pip install -r requirements.txt')
```

## Imports

To create the API, we need to import the function _Flask_ from the module _flask_ and the functions _Resource_, _Api_ and _reqparse_ from the module _flask\_restful_.
We also import the modules json, pandas, numpy and combinations.


```python
from flask import Flask # imported to create the api
from flask_restful import Resource, Api, reqparse # imported to create the api

import json
import pandas as pd
import numpy as np
from itertools import combinations
```

## Definition of some useful functions

_Remark: Of course, these functions would have been commented if I had had a bit more time._

```python
def preprocessing(data):

  def make_groups(df, cumulate=False):
    df['p_range']=df['pmax']-df['pmin']
    groups=pd.DataFrame()
    for price in df['price'].unique():
      subgroup = df.loc[df['price']==price,:].sort_values(by='pmin', ascending=True).reset_index()
      n_index = len(subgroup.index)
      comb = list(combinations(subgroup.index, 2))
      idx=0
      while (n_index>=2)&(idx<=len(comb)-1):
        units = subgroup.loc[list(comb[idx]),:]
        if (units['pmin'].iloc[1]<units['pmax'].iloc[0])&(units['pmin'].iloc[0]<units['p_range'].iloc[1]):
          units=pd.DataFrame.from_dict({'name':[[units['name'].iloc[0], units['name'].iloc[1]]], 'pmin':[units['pmin'].min()], 'pmax':[units['pmax'].sum()], 
                                        'price':[units['price'].iloc[0]]})
          units['p_range']=units['pmax']-units['pmin']
          subgroup=pd.concat([units, subgroup.loc[subgroup.index.drop(list(comb[idx])),:]], axis=0).sort_values(by='pmin', ascending=True).reset_index(drop=True)
          n_index-=1
          if n_index>=2:
            comb = list(combinations(subgroup.index, 2))
            idx=0
        else:
          idx+=1
      groups = pd.concat([groups, subgroup], axis=0)
    return groups.loc[:,['name','pmin','pmax','price']]

  load = data["load"]
  fuels = pd.Series(data["fuels"])
  powerplants = pd.DataFrame(data["powerplants"])

  prices = {'gasfired':fuels.loc['gas(euro/MWh)'], 'turbojet':fuels.loc['kerosine(euro/MWh)'], 'windturbine':0}
  powerplants['fuel_prices'] = powerplants.type.replace(prices)

  powerplants['actual_efficiency'] = powerplants['efficiency']
  wind_idx = powerplants['type']=='windturbine'
  powerplants.loc[wind_idx, 'actual_efficiency'] = fuels.loc['wind(%)']/100
  powerplants.loc[wind_idx, 'pmax'] *= powerplants.loc[wind_idx, 'actual_efficiency']

  floor = lambda x: ((10*x)//1)/10
  ceil = lambda x: ((10*x)//1 + int((10*x)%1>0))/10
  powerplants['pmin'] = powerplants['pmin'].apply(ceil)
  powerplants['pmin'] = powerplants['pmin'].apply(floor)
  powerplants['price'] = powerplants['fuel_prices']/powerplants['actual_efficiency']
  powerplants['name']=powerplants['name'].apply(lambda x:[x])
  powerplants = powerplants.sort_values(by=['price','pmin'], ascending=True).reset_index(drop=True) 

  wind_turbines = powerplants.loc[powerplants['type']=='windturbine',:]
  wind_turbines = pd.DataFrame.from_dict({'name':[wind_turbines['name'].sum()], 'pmin':[wind_turbines['pmin'].min()], 'pmax':[wind_turbines['pmax'].sum()], 'price':[wind_turbines['price'].min()]})
  groups = powerplants.loc[powerplants['type']!='windturbine',['name','pmin','pmax','price']]
  groups=make_groups(groups)
  
  groups = pd.concat([wind_turbines, groups], axis=0, ignore_index=True)
  
  return powerplants, groups, load
  

def get_strategy(groups, load):
    
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

  return strategy, best_price


def share(x, load, powerplants):
  results={}
  if len(x)==1:
    results[x[0]]=load
    return results
  else:
    name1 = x[0]
    name2 = x[1]
    if len(x[0])==1:
      if load<powerplants.loc[powerplants['name'].apply(str)==str(name2), 'pmin'].iloc[0]:
        results[name1[0]]=load
      elif (powerplants.loc[powerplants['name'].apply(str)==str(name2), 'pmin'].iloc[0]<load)&(load<powerplants.loc[powerplants['name'].apply(str)==str(name2), 'pmax'].iloc[0]):
        results[name2[0]]=load
      else:
        results[name2[0]]=round(min(load,powerplants.loc[powerplants['name'].apply(str)==str(name2), 'pmax'].iloc[0]),1)
        results[name1[0]]=round(load-results[name2[0]],1)
    else:
      if load<powerplants.loc[powerplants['name'].apply(str)==str(name2), 'pmin'].iloc[0]:
        results[str(name1)]=load
      elif (powerplants.loc[powerplants['name'].apply(str)==str(name2), 'pmin'].iloc[0]<load)&(load<powerplants.loc[powerplants['name'].apply(str)==str(name2), 'pmax'].iloc[0]):
        results[name2[0]]=load
      else:
        results = share(x[0], load-powerplants.loc[powerplants['name'].apply(str)==str(name2), 'pmax'].iloc[0], powerplants)
        results[name2[0]] = round(powerplants.loc[powerplants['name'].apply(str)==str(name2), 'pmax'].iloc[0],1)
    return results


def get_results(strategy, groups, powerplants, share=share):
  results = []
  for (p,unit) in zip(strategy['p'], strategy['units']):
    if unit==0: # hangle wind case
      for name in groups.loc[unit,'name']:
        commitment=round(min(p, powerplants.loc[powerplants['name'].apply(lambda x:x[0])==name, 'pmax'].iloc[0]),1)
        results.append({"name":name, "p":str(round(min(p, commitment),1))})
        p-=commitment
        if p==0:
          break
    else:
      group_results = share(groups.loc[unit, 'name'], p, powerplants)
      for item in group_results.items():
        results.append({"name":str(item[0]), "p":str(item[1])})
  for name in powerplants.name.apply(lambda x:x[0]):
    if name not in [result['name'] for result in results]:
      results.append({"name":name, "p":str(0)})
  return results


def plan(data):
    powerplants, groups, load = preprocessing(data)
    strategy, best_price=get_strategy(groups, load)
    results = get_results(strategy, groups, powerplants, share)
    return results
```

## Initialization of the API

The Api is initialized with the following lines of code.


```python
app = Flask(__name__)
api = Api(app)
```

## Endpoint creation

Creation of a ProductionPlan class. 
 - We pass _Resource_ in the the class definition so that Flask know that this class is an endpoint for our API.
 - We include our POST method inside the class.
 - We link our ProductionPlan class with the /productionplan endpoint using api.add_resource.
 
 _Remark: the following code uses the function plan previously defined._


```python
class ProductionPlan(Resource): # pass Resource
    def post(self): # define our post method
        parser = reqparse.RequestParser()
        parser.add_argument('name', required=True)
        args = parser.parse_args()
        
        # read the json
        data = json.load(open('{}.json'.format(args['name'])))
        if data['load']!=round(data['load'],1):
            return {
                'ValueError': "load is not a multiple of 0.1 MW"
            }, 500
        results=plan(data)
        json.dump(results, open('response_'+args['name'], 'w'))
        return results, 200

api.add_resource(ProductionPlan, '/productionplan') # link the class with the endpoint
```

## Running the API

The API is run thanks to the following lines of code. The use of the argument _port_ enables us to expose the API on a specified port (8888 in this case).


```python
if __name__ == '__main__':
    app.run(port=8888)  # run our Flask app on port 8888
```

To run the script, open a terminal and write _ipython  gem_spaas_challenge.py_.

<img src='image1.png'>

The code will automatically install the dependencies and you should then see something like this.

<img src='image2.png'>

## Use the API

We can use our API with Postman. Download Postman from here : https://www.postman.com/downloads/

Once you have download postman, your will see a new postman file in your download folder (in my case, I downloaded the Linux 64-bit version and the file is named _Postman-linux-x86_64-8.12.4.tar.gz_). Extract it. Open the resulting _Postman_ folder. Then open the _app_ folder and execute the _Postman_ executable file.<br>

Once Postman is open on your computer, click on _POST_ to create a _POST_ request and write _http://127.0.0.1:8888/productionplan?name=payload1_. You should replace _payload1_ by the name of your payload json file. Of course, this payload file has to be in the right folder (the current working directory of your python script, which is normally your user folder). Thus, you will obtain a result like this one.<br>
<img src='image3.png'>

