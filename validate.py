#!/usr/bin/env python3

import random
import os
import sys
import signal
import subprocess

import eth_account
import algosdk
import requests
import json
from time import sleep

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import Base, Order

endpoint_url = "http://localhost"
endpoint_port = 5002
db_name = "orders.db"

def is_port_in_use(port):
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0


def validate(student_repo_path="/home/codio/workspace"):
    try:
        log = open( "server_log.txt", "a" )
    except Exception as e:
        print( "Can't open server_log.txt" )
        print( e )
    already_running = False
    if is_port_in_use(endpoint_port):
        already_running = True
        print( "Flask server is already running" )
    else:
        print( "Starting Flask server" )
        try:
            flask_server = subprocess.Popen(["python3", "database_endpoint.py"],
                                        stdout=log,
                                        stderr=log,
										cwd=student_repo_path,
                                        shell=False,
                                        preexec_fn=os.setsid)
            #out, err = flask_server.communicate()
            #if err:
            #     print('The verification_endpoint raised an error:', err.decode())
            #else:
            #    print("Started Flask server!")
            try:
                outs, errs = flask_server.communicate(timeout=5)
                print( f"Errors = {errs}" )
            except subprocess.TimeoutExpired:
                pass
            except Exception as e:
                print( "Flask process exception" )
                print( e )
            if flask_server.poll() is not None:
                print( "Error: Flask server stopped" )
        except Exception as e:
            print( e )
            print( "Failed" )
            return 0

    sleep(2)
          
    num_tests = 5
    num_passed = 0

    for _ in range(num_tests):
        try:
            num_passed += test_endpoint()
        except Exception as e:
            print( f"test_endpoint() failed: {e}" )
            continue

    print( f"Passed {num_passed}/{4*num_tests} tests" )

    #Check if a straight db call returns the same thing as the endpoint
    ob1 = get_order_book()
    ob2 = test_db(student_repo_path)
    fields = ['sender_pk','receiver_pk','buy_currency','sell_currency','buy_amount','sell_amount']
    ob3= [ {field: t[field] for field in fields} for t in ob1 ] 
    ob4= [ {field: t[field] for field in fields} for t in ob2 ] 
    if not dict_list_eq(ob3,ob4):
        print( "get_order_book returns a different result from the database!" )

    #Kill the server
    if not already_running:
        try:
            log.close()
            os.killpg(os.getpgid(flask_server.pid), signal.SIGTERM)
        except ProcessLookupError:
            pass

    return num_passed

def dict_list_eq(l1, l2):
    """"
        Given two lists of dictionaries, l1 and l2, check if the two lists have the same elements (possibly in different orders)
    """
    sorted_l1 = sorted([sorted([p for p in d.items() if p[1] is not None]) for d in l1])
    sorted_l2 = sorted([sorted([p for p in d.items() if p[1] is not None]) for d in l2])
    if sorted_l1 != sorted_l2:
        for a,b in zip( sorted_l1,sorted_l2 ):
            if a != b:
                print( a )
                print( b )
    return sorted_l1 == sorted_l2

def send_signed_msg(platform,order_dict,sk,real=True):
    """
        sign the message given by the dict 'order_dict' using the secret key sk
        platform should be Algorand or Ethereum and the signing algorithm depends on the platform variable
        the signed message is then posted to the exchange endpoint /trade
        if real == False, then the message is tweaked before sending so the signature will *not* validate
    """
    msg_dict = { 'platform': platform }
    msg_dict.update( order_dict )
    if platform == "Ethereum":
        msg = json.dumps(msg_dict)
        eth_encoded_msg = eth_account.messages.encode_defunct(text=msg)
        eth_sig_obj = eth_account.Account.sign_message(eth_encoded_msg,sk)
        sig = eth_sig_obj.signature.hex() #.hex converts HexBytes object a string (which is JSON serializable)
    if platform == "Algorand":
        msg = json.dumps(msg_dict)
        alg_encoded_msg = msg.encode('utf-8')
        sig = algo_sig_str = algosdk.util.sign_bytes(alg_encoded_msg,sk)
    
    if not real:
         msg_dict['buy_amount'] += 2
    post_dict = { 'sig': sig, 'payload': msg_dict }
    try:
        res = requests.post( endpoint_url + ":" + str(endpoint_port) + "/trade", json=post_dict )
    except Exception as e:
        res = None
        print( "Error in send_signed_msg" )
        print( "=====" )
        print( post_dict )
        print( "=====" )
        print( e )
    try:
        res_json = res.json()
    except Exception as e:
        print( "Error in send_signed_msg" )
        print( "Can't jsonify result" )
        print( e ) 
        res_json = ""

    return res_json

def get_order_book():
    """
    Get the current state of the order book from the endpoint /order_book
    retruns a list of dicts
    """
    try:
        res = requests.get( endpoint_url + ":" + str(endpoint_port) + "/order_book", json={} ).json()
    except Exception as e:
        print( "endpoint /order_book failed" )
        print( e ) 
        return []
    fields = ['buy_currency','sell_currency','buy_amount','sell_amount', 'signature', 'sender_pk', 'receiver_pk' ]
    try:
        order_book = [ {field: t[field] for field in fields} for t in res['data']] 
    except Exception as e:
        print( "/order_book returned an invalid response" )
        print( e )
        return []
    return order_book

def test_endpoint():
    num_passed = 0
    for real in [True, False]:
        num_passed += test_Algo(real)
        num_passed += test_Eth(real)
    return num_passed

def test_db(student_repo_path="/home/codio/workspace"):
    fields = ['sender_pk','receiver_pk','buy_currency','sell_currency','buy_amount','sell_amount', 'signature']
    try:
        db_path = student_repo_path + '/' + db_name
        engine = create_engine('sqlite:///'+db_path)
        Base.metadata.bind = engine
        DBSession = sessionmaker(bind=engine)
        session = DBSession()
    except Exception as e:
        print( e )
        print( "Couldn't connect to DB" )
        return None
    try:
        query = session.query(Order)
        result = [{field:getattr(u,field)for field in fields} for u in query.all()]
    except Exception as e:
        print( "Connection failed" )
    return result

def test_Algo(real=True):
    algo_sk, algo_pk = algosdk.account.generate_account()
    platform = "Algorand"
 
    order_dict = {}
    order_dict['sender_pk'] = algo_pk
    order_dict['receiver_pk'] = hex(random.randint(0,2**256))[2:] 
    order_dict['buy_currency'] = "Ethereum"
    order_dict['sell_currency'] = "Algorand"
    order_dict['buy_amount'] = random.randint(1000,10000)
    order_dict['sell_amount'] = random.randint(1,3)*order_dict['buy_amount']
    response = send_signed_msg( platform, order_dict, algo_sk, real )

    order_book = get_order_book()
    if real:
        for order in order_book:
            if all( order[k] == order_dict[k] for k in order_dict.keys() ):
                print('Passed real algorand case')
                return True
        print('Failed real algorand case')
        return False
    else:
        for order in order_book:
            if all( order[k] == order_dict[k] for k in order_dict.keys() ):
                print('Failed fake algorand case')
                return False
        print('Passed fake algorand case')
        return True
    print( "Shouldn't get here" )

def test_Eth(real=True):
    eth_account.Account.enable_unaudited_hdwallet_features()
    acct, mnemonic = eth_account.Account.create_with_mnemonic()

    eth_pk = acct.address
    eth_sk = acct.key
    platform = "Ethereum"

    order_dict = {}
    order_dict['sender_pk'] = eth_pk
    order_dict['receiver_pk'] = hex(random.randint(0,2**256))[2:] 
    order_dict['buy_currency'] = "Algorand"
    order_dict['sell_currency'] = "Ethereum"
    order_dict['sell_amount'] = random.randint(1000,10000)
    order_dict['buy_amount'] = random.randint(1,3)*order_dict['sell_amount']

    response = send_signed_msg( platform, order_dict, eth_sk, real )

    order_book = get_order_book()
    if real:
        for order in order_book:
            if all( order[k] == order_dict[k] for k in order_dict.keys() ):
                print( "Passed real eth case" )
                return True
        print("Failed real eth case")
        return False
    else:
        for order in order_book:
            if all( order[k] == order_dict[k] for k in order_dict.keys() ):
                print("Failed fake eth case")
                return False
        print( "Passed fake eth case" )
        return True
    print( "Shouldn't get here" )
