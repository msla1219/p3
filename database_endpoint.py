from flask import Flask, request, g
from flask_restful import Resource, Api
from sqlalchemy import create_engine, select, MetaData, Table
from flask import jsonify
import json
import eth_account
import algosdk
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm import scoped_session
from sqlalchemy.orm import load_only

from models import Base, Order, Log
engine = create_engine('sqlite:///orders.db')
Base.metadata.bind = engine
DBSession = sessionmaker(bind=engine)

app = Flask(__name__)

#These decorators allow you to use g.session to access the database inside the request code
@app.before_request
def create_session():
    g.session = scoped_session(DBSession) #g is an "application global" https://flask.palletsprojects.com/en/1.1.x/api/#application-globals

@app.teardown_appcontext
def shutdown_session(response_or_exc):
    g.session.commit()
    g.session.remove()

"""
-------- Helper methods (feel free to add your own!) -------
"""
def verify(content):

    try:

        if content['payload']['platform'] == 'Ethereum':
            eth_sk = content['sig']
            eth_pk = content['payload']['sender_pk']

            payload = json.dumps(content['payload'])
            eth_encoded_msg = eth_account.messages.encode_defunct(text=payload)
            recovered_pk = eth_account.Account.recover_message(eth_encoded_msg, signature=eth_sk)

            # Check if signature is valid
            if recovered_pk == eth_pk:
                result = True
            else:
                result = False

            return result           # bool value

        if content['payload']['platform'] == 'Algorand':
            algo_sig = content['sig']
            algo_pk = content['payload']['sender_pk']
            payload = json.dumps(content['payload'])
            
            result = algosdk.util.verify_bytes(payload.encode('utf-8'), algo_sig, algo_pk)
            return result           # bool value 

    except Exception as e:
        import traceback
        print(traceback.format_exc())
        print(e)

        
def insert_order(content):
    
    try:
        # Insert new order
        order_obj = Order(sender_pk=content['payload']['sender_pk'],
                          receiver_pk=content['payload']['receiver_pk'], 
                          buy_currency=content['payload']['buy_currency'], 
                          sell_currency=content['payload']['sell_currency'], 
                          buy_amount=content['payload']['buy_amount'], 
                          sell_amount=content['payload']['sell_amount'], 
                          exchange_rate=(content['payload']['buy_amount']/content['payload']['sell_amount']),
                          signature=content['sig'])

        g.session.add(order_obj)
        g.session.commit()


    except Exception as e:
        import traceback
        print(traceback.format_exc())
        print(e)
        
        
def log_message(d):
    # Takes input dictionary d and writes it to the Log table

    payload = json.dumps(d['payload'])

    try:
        # Insert new log
        log_obj = Log(message = json.dumps(d['payload']))

        g.session.add(log_obj)
        g.session.commit()

    except Exception as e:
        import traceback
        print(traceback.format_exc())
        print(e)
        
    

"""
---------------- Endpoints ----------------
"""
    
@app.route('/trade', methods=['POST'])
def trade():
    
    try:

        if request.method == "POST":
            content = request.get_json(silent=True)
            print( f"content = {json.dumps(content)}" )
            columns = [ "sender_pk", "receiver_pk", "buy_currency", "sell_currency", "buy_amount", "sell_amount", "platform" ]
            fields = [ "sig", "payload" ]
            error = False
            for field in fields:
                if not field in content.keys():
                    print( f"{field} not received by Trade" )
                    print( json.dumps(content) )
                    log_message(content)
                    return jsonify( False )

            error = False
            for column in columns:
                if not column in content['payload'].keys():
                    print( f"{column} not received by Trade" )
                    error = True
            if error:
                print( json.dumps(content) )
                log_message(content)
                return jsonify( False )

            #Your code here
            #Note that you can access the database session using g.session
            if verify(content) is True: 
                insert_order(content)
            else:
                log_message(content)
            
            return jsonify( True )

    except Exception as e:
        import traceback
        print(traceback.format_exc())
        print(e)

@app.route('/order_book')
def order_book():
    #Your code here
    #Note that you can access the database session using g.session

    try:
        results = g.session.execute("select sender_pk, receiver_pk, buy_currency, sell_currency, buy_amount, sell_amount, signature " + 
                            "from orders ")

        result_list = list()
        for row in results:
            item = dict()
            item['sender_pk'] = row['sender_pk']
            item['receiver_pk'] = row['receiver_pk']
            item['buy_currency'] = row['buy_currency']
            item['sell_currency'] = row['sell_currency']
            item['buy_amount'] = row['buy_amount']
            item['sell_amount'] = row['sell_amount']
            item['signature'] = row['signature']

            result_list.append(item)

        result = dict()
        result['data'] = result_list
    
        return jsonify(result)
    
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        print(e)
    

if __name__ == '__main__':
    app.run(port='5002')
