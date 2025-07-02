import os
import time
import json
import logging
from typing import Dict, Any, List, Optional

import requests
from web3 import Web3, exceptions
from web3.types import LogReceipt
from dotenv import load_dotenv

# --- Configuration & Setup ---

# Load environment variables from .env file
load_dotenv()

# Setup basic logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# --- Constants ---

# Number of block confirmations to wait for before processing an event.
# This helps mitigate risks from blockchain reorganizations (reorgs).
CONFIRMATION_BLOCKS = 12

# Interval in seconds to poll for new blocks.
POLL_INTERVAL_SECONDS = 15

# File to store the last processed block number for persistence.
STATE_FILE = 'listener_state.json'

# --- Core Classes ---

class ChainConnector:
    """
    Handles the connection and basic interactions with an Ethereum-like blockchain node.
    It's designed to be a simple, reusable wrapper around the Web3.py library.
    """
    def __init__(self, rpc_url: str):
        """
        Initializes the connector with a given RPC URL.
        
        Args:
            rpc_url (str): The HTTP or WebSocket URL of the blockchain node.
        """
        self.rpc_url = rpc_url
        try:
            self.w3 = Web3(Web3.HTTPProvider(self.rpc_url))
            if not self.w3.is_connected():
                raise ConnectionError(f"Failed to connect to RPC endpoint: {rpc_url}")
            logging.info(f"Successfully connected to chain via {rpc_url}. Chain ID: {self.w3.eth.chain_id}")
        except Exception as e:
            logging.error(f"Error initializing Web3 connection: {e}")
            raise

    def get_latest_block_number(self) -> int:
        """
        Fetches the most recent block number from the connected chain.
        
        Returns:
            int: The latest block number.
        
        Raises:
            ConnectionError: If the connection to the node fails.
        """
        try:
            return self.w3.eth.block_number
        except exceptions.ProviderConnectionError as e:
            logging.error(f"Could not fetch latest block number. Provider connection error: {e}")
            raise ConnectionError("Provider connection failed.") from e

    def get_logs(self, from_block: int, to_block: int, address: str, topics: List[str]) -> List[LogReceipt]:
        """
        Retrieves event logs from a specified block range for a given contract address and topics.
        
        Args:
            from_block (int): The starting block number (inclusive).
            to_block (int): The ending block number (inclusive).
            address (str): The contract address to filter events from.
            topics (List[str]): A list of event topic hashes to filter by.
            
        Returns:
            List[LogReceipt]: A list of event logs matching the filter.
        """
        try:
            filter_params = {
                'fromBlock': from_block,
                'toBlock': to_block,
                'address': address,
                'topics': topics
            }
            return self.w3.eth.get_logs(filter_params)
        except Exception as e:
            logging.error(f"An error occurred while fetching logs: {e}")
            return []

class EventDataParser:
    """
    A utility class with static methods to parse raw event log data.
    In a real-world application, this would use the contract ABI for accurate decoding.
    For this simulation, it performs a simplified parsing.
    """
    @staticmethod
    def parse_token_locked_event(log: LogReceipt) -> Optional[Dict[str, Any]]:
        """
        Parses a 'TokensLocked' event log.
        
        Simulated Event Signature: 
        TokensLocked(address indexed user, address indexed token, uint256 amount, uint256 destinationChainId)
        
        Args:
            log (LogReceipt): The raw event log from Web3.py.
        
        Returns:
            Optional[Dict[str, Any]]: A dictionary with parsed event data or None if parsing fails.
        """
        try:
            # NOTE: This is a simplified simulation. In a real implementation, you would use:
            # from web3.contract import Contract
            # contract_abi = [...] 
            # contract = w3.eth.contract(address=..., abi=contract_abi)
            # parsed_log = contract.events.TokensLocked().process_log(log)
            # return parsed_log['args']
            
            tx_hash = log['transactionHash'].hex()
            block_number = log['blockNumber']
            
            # Simplified parsing based on topic and data positions
            user_address = '0x' + log['topics'][1].hex()[26:]
            token_address = '0x' + log['topics'][2].hex()[26:]
            
            # Data is a hex string, split it into 32-byte chunks
            data = log['data'].hex().lstrip('0x')
            amount_raw = int(data[0:64], 16)
            destination_chain_id = int(data[64:128], 16)
            
            parsed_data = {
                'transactionHash': tx_hash,
                'blockNumber': block_number,
                'user': user_address,
                'token': token_address,
                'amount': amount_raw,
                'destinationChainId': destination_chain_id
            }
            logging.info(f"Parsed event from tx {tx_hash}: {parsed_data}")
            return parsed_data
        except (IndexError, ValueError) as e:
            logging.error(f"Failed to parse event log {log['transactionHash'].hex()}: {e}")
            return None

class DestinationChainHandler:
    """
    Handles the logic for the destination chain. In this simulation, it notifies a hypothetical 
    off-chain relayer service via an API call to process the token minting/unlocking.
    """
    def __init__(self, relayer_api_endpoint: str):
        """
        Initializes the handler with the relayer's API endpoint.
        
        Args:
            relayer_api_endpoint (str): The URL of the relayer service.
        """
        self.api_endpoint = relayer_api_endpoint
        self.session = requests.Session()
        self.session.headers.update({'Content-Type': 'application/json'})

    def trigger_token_mint(self, event_data: Dict[str, Any]) -> bool:
        """
        Sends the parsed event data to the relayer service.
        
        Args:
            event_data (Dict[str, Any]): The data from the source chain event.
        
        Returns:
            bool: True if the relayer acknowledged the request successfully, False otherwise.
        """
        logging.info(f"Triggering action on destination chain for tx {event_data['transactionHash']}")
        payload = {
            'sourceTransactionHash': event_data['transactionHash'],
            'recipient': event_data['user'],
            'tokenAddress': event_data['token'],
            'amount': event_data['amount'],
            'targetChainId': event_data['destinationChainId']
        }

        try:
            response = self.session.post(self.api_endpoint, json=payload, timeout=10)
            response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)
            
            if response.status_code == 200 or response.status_code == 202:
                logging.info(f"Successfully notified relayer for tx {event_data['transactionHash']}. Response: {response.json()}")
                return True
            else:
                logging.warning(f"Relayer returned an unexpected status code {response.status_code} for tx {event_data['transactionHash']}")
                return False
        except requests.exceptions.RequestException as e:
            logging.error(f"Failed to communicate with relayer service for tx {event_data['transactionHash']}: {e}")
            return False


class BridgeEventListener:
    """
    The main orchestrator class. It connects all components together, manages state, 
    and runs the main event listening loop.
    """
    def __init__(self, config: Dict[str, Any]):
        """
        Initializes the listener with a configuration dictionary.
        
        Args:
            config (Dict[str, Any]): A dictionary containing RPC URL, contract address, etc.
        """
        self.config = config
        self.connector = ChainConnector(config['rpc_url'])
        self.destination_handler = DestinationChainHandler(config['relayer_api_endpoint'])
        
        self.state = self._load_state()
        self.processed_txs = set(self.state.get('processed_txs', []))

    def _load_state(self) -> Dict[str, Any]:
        """
        Loads the listener's state from a file to resume from where it left off.
        """
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, 'r') as f:
                state = json.load(f)
                logging.info(f"Loaded state from {STATE_FILE}: {state}")
                return state
        else:
            # If no state file, start from the current block or a configured starting block
            start_block = self.config.get('start_block', self.connector.get_latest_block_number())
            logging.info(f"No state file found. Starting scan from block {start_block}")
            return {'last_scanned_block': start_block, 'processed_txs': []}

    def _save_state(self):
        """
        Saves the current state (last scanned block, processed txs) to a file.
        """
        state_to_save = {
            'last_scanned_block': self.state['last_scanned_block'],
            'processed_txs': list(self.processed_txs) # Convert set to list for JSON serialization
        }
        with open(STATE_FILE, 'w') as f:
            json.dump(state_to_save, f, indent=4)
        logging.info(f"Saved state to {STATE_FILE}")

    def _scan_blocks(self):
        """
        Performs one cycle of scanning blocks for relevant events.
        """
        try:
            latest_block = self.connector.get_latest_block_number()
            from_block = self.state['last_scanned_block'] + 1
            # We scan up to `latest_block - CONFIRMATION_BLOCKS` to ensure event finality.
            to_block = latest_block - CONFIRMATION_BLOCKS

            if from_block > to_block:
                logging.info(f"No new blocks to scan. Current head: {latest_block}, waiting for {CONFIRMATION_BLOCKS} confirmations.")
                return

            logging.info(f"Scanning blocks from {from_block} to {to_block}...")

            logs = self.connector.get_logs(
                from_block=from_block,
                to_block=to_block,
                address=self.config['bridge_contract_address'],
                topics=[self.config['event_topic_hash']]
            )

            if logs:
                logging.info(f"Found {len(logs)} potential event(s) in block range.")
                for log in logs:
                    self._process_log(log)
            else:
                logging.info("No relevant events found in this range.")

            # Update state with the last block we scanned successfully.
            self.state['last_scanned_block'] = to_block

        except ConnectionError:
            logging.error("Connection error during block scan. Will retry later.")
        except Exception as e:
            logging.error(f"An unexpected error occurred during block scan: {e}", exc_info=True)

    def _process_log(self, log: LogReceipt):
        """
        Processes a single event log: parse, check for duplicates, and trigger handler.
        """
        tx_hash = log['transactionHash'].hex()
        if tx_hash in self.processed_txs:
            logging.warning(f"Skipping already processed transaction: {tx_hash}")
            return
        
        parsed_event = EventDataParser.parse_token_locked_event(log)
        if not parsed_event:
            return
        
        # Trigger the action on the destination chain
        success = self.destination_handler.trigger_token_mint(parsed_event)
        
        if success:
            self.processed_txs.add(tx_hash)
            logging.info(f"Successfully processed event from tx {tx_hash}")
        else:
            logging.error(f"Failed to process event from tx {tx_hash}. Will be retried on next scan.")

    def run(self):
        """
        The main execution loop for the event listener.
        It periodically calls the block scanner and handles graceful shutdown.
        """
        logging.info("Starting Cross-Chain Bridge Event Listener...")
        try:
            while True:
                self._scan_blocks()
                logging.info(f"Sleeping for {POLL_INTERVAL_SECONDS} seconds until next poll.")
                time.sleep(POLL_INTERVAL_SECONDS)
        except KeyboardInterrupt:
            logging.info("Shutdown signal received. Exiting gracefully.")
        finally:
            self._save_state()
            logging.info("Listener has been shut down.")

# --- Main Execution ---

def main():
    """
    Entry point of the script. Loads configuration and starts the listener.
    """
    # Keccak-256 hash of the event signature. E.g., for 'TokensLocked(address,address,uint256,uint256)'
    # you can get this hash from a tool like https://emn178.github.io/online-tools/keccak_256.html
    # or using web3.py: Web3.keccak(text='TokensLocked(address,address,uint256,uint256)').hex()
    TOKENS_LOCKED_EVENT_HASH = os.getenv('TOKENS_LOCKED_EVENT_HASH', '0x123...') # Replace with your actual event hash

    config = {
        'rpc_url': os.getenv('SOURCE_CHAIN_RPC_URL'),
        'bridge_contract_address': os.getenv('BRIDGE_CONTRACT_ADDRESS'),
        'relayer_api_endpoint': os.getenv('RELAYER_API_ENDPOINT', 'https://api.example-relayer.com/submit'),
        'event_topic_hash': TOKENS_LOCKED_EVENT_HASH,
        'start_block': int(os.getenv('START_BLOCK', '0'))
    }

    # Validate configuration
    if not all([config['rpc_url'], config['bridge_contract_address'], config['event_topic_hash']]):
        logging.error("Missing critical environment variables: SOURCE_CHAIN_RPC_URL, BRIDGE_CONTRACT_ADDRESS, TOKENS_LOCKED_EVENT_HASH")
        return

    listener = BridgeEventListener(config)
    listener.run()

if __name__ == "__main__":
    main()
