# {repo_name}: A Cross-Chain Bridge Event Listener

This repository contains a Python-based event listener designed to monitor a smart contract on a source blockchain and trigger actions on a destination chain. It serves as a foundational component for a cross-chain bridge, acting as a relayer or oracle that securely transfers information between two distinct blockchain networks.

This script is architected for robustness, persistence, and modularity, making it a suitable blueprint for production-grade decentralized applications.

## Concept

Blockchains are inherently isolated ledgers. A cross-chain bridge enables the transfer of assets or data from one blockchain (e.g., Ethereum) to another (e.g., Polygon). This is typically achieved through a lock-and-mint or burn-and-release mechanism.

This event listener plays a crucial role in this process:
1.  **Listen**: It continuously monitors a `Bridge` smart contract on the source chain.
2.  **Detect**: When a user locks tokens in the contract, it emits an event (e.g., `TokensLocked`). The listener detects this event.
3.  **Verify**: It waits for a certain number of block confirmations to ensure the transaction is final and not part of a blockchain reorganization (reorg).
4.  **Relay**: After verification, it securely communicates the event data to a component responsible for the destination chain.
5.  **Act**: The destination chain component (simulated here as a relayer API) receives the data and proceeds to mint an equivalent amount of wrapped tokens for the user on the destination chain.

This script simulates the 'Listen', 'Detect', 'Verify', and 'Relay' steps.

## Code Architecture

The script is designed with a clear separation of concerns, embodied in several key classes:

*   `ChainConnector`:
    *   **Responsibility**: Manages the connection to the source blockchain's RPC endpoint using `web3.py`.
    *   **Functionality**: Provides methods to fetch the latest block number and query for event logs within a specific block range.

*   `EventDataParser`:
    *   **Responsibility**: Decouples the logic of parsing raw event logs.
    *   **Functionality**: Contains static methods to transform a raw log from `web3.py` into a structured, human-readable dictionary. In a real application, this would use the contract's ABI for precise decoding.

*   `DestinationChainHandler`:
    *   **Responsibility**: Encapsulates all logic related to interacting with the destination chain.
    *   **Functionality**: In this simulation, it makes an HTTP POST request to a hypothetical relayer service API using the `requests` library. This is a common pattern where off-chain relayers are responsible for submitting transactions on the destination chain.

*   `BridgeEventListener`:
    *   **Responsibility**: The central orchestrator. It ties all other components together and manages the application's main loop and state.
    *   **Functionality**: 
        *   Initializes all helper classes.
        *   Manages a persistent state (`listener_state.json`) to keep track of the last block it scanned. This allows the listener to be stopped and restarted without reprocessing old events or missing new ones.
        *   Contains the main `run()` loop that periodically polls the blockchain for new blocks.
        *   Handles graceful shutdowns, ensuring the state is saved before exiting.

## How it Works

The operational flow of the listener is as follows:

1.  **Initialization**: 
    *   The script loads configuration from a `.env` file (RPC URLs, contract addresses, etc.).
    *   It attempts to load `listener_state.json`. If the file exists, it resumes scanning from the `last_scanned_block`. If not, it starts from a configured `START_BLOCK` or the current chain head.

2.  **Main Loop**: 
    *   The listener enters an infinite loop, polling at a defined interval (`POLL_INTERVAL_SECONDS`).

3.  **Block Scanning**: 
    *   In each iteration, it fetches the current latest block number from the source chain.
    *   It defines a block range to scan: from `last_scanned_block + 1` up to `latest_block - CONFIRMATION_BLOCKS`.
    *   Waiting for confirmations is a critical security measure against reorgs. An event is only considered final after several new blocks have been mined on top of it.

4.  **Event Filtering**: 
    *   It uses `eth_getLogs` via the `ChainConnector` to query for logs within the calculated block range that match the bridge contract's address and the specific event topic hash (e.g., the signature of `TokensLocked`).

5.  **Event Processing**: 
    *   For each log found:
        *   It checks if the transaction hash has already been processed to prevent duplicates.
        *   The `EventDataParser` decodes the log's data.
        *   The `DestinationChainHandler` is called, which sends the parsed data to the relayer API.
        *   If the relayer API confirms receipt, the transaction hash is added to the `processed_txs` set.

6.  **State Management**: 
    *   After scanning a range, the `last_scanned_block` in the state is updated to the end of that range.
    *   The state is saved to `listener_state.json` upon graceful shutdown (e.g., via Ctrl+C).

## Usage Example

Follow these steps to set up and run the event listener.

**1. Clone the repository:**
```bash
git clone https://github.com/your-username/{repo_name}.git
cd {repo_name}
```

**2. Create a Python virtual environment:**
```bash
python3 -m venv venv
source venv/bin/activate
# On Windows: venv\Scripts\activate
```

**3. Install dependencies:**
```bash
pip install -r requirements.txt
```

**4. Create a configuration file:**

Create a file named `.env` in the root directory and populate it with the following details. You can get a free RPC URL from services like Infura, Alchemy, or Ankr.

```env
# RPC URL for the source blockchain (e.g., Ethereum, Goerli, Sepolia)
SOURCE_CHAIN_RPC_URL="https://mainnet.infura.io/v3/your-infura-project-id"

# The address of the bridge smart contract you want to listen to
BRIDGE_CONTRACT_ADDRESS="0x1234567890123456789012345678901234567890"

# The Keccak-256 hash of the event signature you are listening for.
# For 'TokensLocked(address,address,uint256,uint256)', this would be:
# 0x1a716c52b22c74e432a688944c5af9fbe798539005a76c4de91353e6f5c531d3
TOKENS_LOCKED_EVENT_HASH="0x1a716c52b22c74e432a688944c5af9fbe798539005a76c4de91353e6f5c531d3"

# (Optional) The API endpoint for the relayer service
RELAYER_API_ENDPOINT="https://api.mock-relayer.com/v1/process-event"

# (Optional) Block number to start scanning from if no state file is found. Defaults to current head.
START_BLOCK="18000000"
```

**5. Run the script:**

```bash
python script.py
```

**Example Output:**

```
2023-10-27 14:30:00 - INFO - Successfully connected to chain via https://.... Chain ID: 1
2023-10-27 14:30:01 - INFO - No state file found. Starting scan from block 18000000
2023-10-27 14:30:01 - INFO - Starting Cross-Chain Bridge Event Listener...
2023-10-27 14:30:01 - INFO - Scanning blocks from 18000001 to 18000150...
2023-10-27 14:30:05 - INFO - No relevant events found in this range.
2023-10-27 14:30:05 - INFO - Sleeping for 15 seconds until next poll.
...
2023-10-27 14:31:20 - INFO - Scanning blocks from 18000151 to 18000162...
2023-10-27 14:31:25 - INFO - Found 1 potential event(s) in block range.
2023-10-27 14:31:25 - INFO - Parsed event from tx 0xabc...: {'transactionHash': '0xabc...', 'blockNumber': 18000155, 'user': '0x...', 'token': '0x...', 'amount': 100000000, 'destinationChainId': 137}
2023-10-27 14:31:25 - INFO - Triggering action on destination chain for tx 0xabc...
2023-10-27 14:31:26 - INFO - Successfully notified relayer for tx 0xabc.... Response: {'status': 'pending', 'queueId': 'xyz-123'}
2023-10-27 14:31:26 - INFO - Successfully processed event from tx 0xabc...
2023-10-27 14:31:26 - INFO - Sleeping for 15 seconds until next poll.
```
