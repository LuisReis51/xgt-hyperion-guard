#!/usr/bin/env python3
"""
HYPERION GUARD - Autonomous Bot Detection System
Monitors XGT token transactions and blacklists wash trading bots
"""

import os
import json
import time
from datetime import datetime
from web3 import Web3
from collections import defaultdict

# Configuration from environment variables
BSC_RPC = os.environ.get('BSC_RPC', 'https://bsc-dataseed.binance.org/')
XGT_CONTRACT = os.environ.get('XGT_CONTRACT', '0x654E38A4516F5476D723D770382A5EaF8Bae0e0D')
LP_PAIR = os.environ.get('LP_PAIR', '0xYourLPPairAddress')
GUARDIAN_PRIVATE_KEY = os.environ.get('GUARDIAN_PRIVATE_KEY')

# Detection thresholds
MIN_TRADES_TO_FLAG = 8
MAX_AVG_HOLD_BLOCKS = 100
WASH_TRADING_THRESHOLD = 0.85
MAX_TRADES_PER_HOUR = 20

# Minimal contract ABI
CONTRACT_ABI = [
    {
        "inputs": [
            {"type": "address", "name": "account"},
            {"type": "string", "name": "reason"}
        ],
        "name": "blacklistAddress",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [{"type": "address", "name": ""}],
        "name": "isBlacklisted",
        "outputs": [{"type": "bool"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "type": "address", "name": "from"},
            {"indexed": True, "type": "address", "name": "to"},
            {"indexed": False, "type": "uint256", "name": "value"}
        ],
        "name": "Transfer",
        "type": "event"
    }
]

class HyperionGuard:
    def __init__(self):
        print("🛡️  HYPERION GUARD - SYSTEM INITIALIZING")
        print("=" * 60)
        
        self.w3 = Web3(Web3.HTTPProvider(BSC_RPC))
        if not self.w3.is_connected():
            raise Exception("❌ Failed to connect to BSC RPC")
        
        print(f"✅ Connected to BSC (Block: {self.w3.eth.block_number})")
        
        self.account = self.w3.eth.account.from_key(GUARDIAN_PRIVATE_KEY)
        print(f"✅ Guardian wallet: {self.account.address}")
        
        self.contract = self.w3.eth.contract(
            address=Web3.to_checksum_address(XGT_CONTRACT),
            abi=CONTRACT_ABI
        )
        self.lp_pair = Web3.to_checksum_address(LP_PAIR)
        
        print(f"✅ XGT Contract: {XGT_CONTRACT}")
        print(f"✅ LP Pair: {LP_PAIR}")
        
        self.load_state()
        print(f"✅ Loaded state (Last block: {self.last_block})")
        print("=" * 60 + "\n")
        
    def load_state(self):
        """Load tracking data from previous runs"""
        try:
            with open('bot_state.json', 'r') as f:
                data = json.load(f)
                self.last_block = data.get('last_block', self.w3.eth.block_number - 1000)
                self.trader_stats = defaultdict(
                    lambda: {'buys': [], 'sells': [], 'trades': [], 'first_seen': 0},
                    {k: v for k, v in data.get('trader_stats', {}).items()}
                )
                self.blacklisted = set(data.get('blacklisted', []))
        except FileNotFoundError:
            print("⚠️  No previous state found, starting fresh")
            self.last_block = self.w3.eth.block_number - 1000
            self.trader_stats = defaultdict(lambda: {
                'buys': [], 'sells': [], 'trades': [], 'first_seen': 0
            })
            self.blacklisted = set()
    
    def save_state(self):
        """Save tracking data for next run"""
        with open('bot_state.json', 'w') as f:
            json.dump({
                'last_block': self.last_block,
                'last_update': datetime.utcnow().isoformat(),
                'trader_stats': {k: v for k, v in self.trader_stats.items()},
                'blacklisted': list(self.blacklisted),
                'total_scanned': len(self.trader_stats),
                'total_blacklisted': len(self.blacklisted)
            }, f, indent=2)
    
    def scan_recent_blocks(self):
        """Scan recent blocks for XGT transfers"""
        current_block = self.w3.eth.block_number
        from_block = max(self.last_block + 1, current_block - 500)
        
        print(f"🔍 Scanning blocks {from_block} → {current_block}...")
        
        try:
            events = self.contract.events.Transfer.get_logs(
                fromBlock=from_block,
                toBlock=current_block
            )
            
            print(f"📊 Found {len(events)} transfers")
            
            for event in events:
                self.analyze_transfer(event)
            
            self.last_block = current_block
            
        except Exception as e:
            print(f"⚠️  Error scanning blocks: {e}")
    
    def analyze_transfer(self, event):
        """Analyze a single transfer event"""
        from_addr = event['args']['from']
        to_addr = event['args']['to']
        amount = event['args']['value']
        block_num = event['blockNumber']
        
        is_buy = (from_addr.lower() == self.lp_pair.lower())
        is_sell = (to_addr.lower() == self.lp_pair.lower())
        
        if not (is_buy or is_sell):
            return
        
        trader = to_addr if is_buy else from_addr
        
        if trader not in self.trader_stats:
            self.trader_stats[trader] = {
                'buys': [], 'sells': [], 'trades': [], 'first_seen': block_num
            }
        
        stats = self.trader_stats[trader]
        trade = {
            'type': 'buy' if is_buy else 'sell',
            'block': block_num,
            'amount': str(amount)
        }
        
        stats['trades'].append(trade)
        if is_buy:
            stats['buys'].append(trade)
        else:
            stats['sells'].append(trade)
        
        if len(stats['trades']) >= MIN_TRADES_TO_FLAG:
            self.check_bot_pattern(trader, stats)
    
    def check_bot_pattern(self, address, stats):
        """Detect bot trading patterns"""
        if address in self.blacklisted:
            return
        
        reasons = []
        
        # Pattern 1: Wash trading
        buy_count = len(stats['buys'])
        sell_count = len(stats['sells'])
        if buy_count > 0 and sell_count > 0:
            wash_ratio = min(buy_count, sell_count) / max(buy_count, sell_count)
            if wash_ratio >= WASH_TRADING_THRESHOLD:
                reasons.append(f"WASH_TRADING ({buy_count}B/{sell_count}S)")
        
        # Pattern 2: Short hold times
        total_hold_blocks = 0
        pairs = 0
        for sell in stats['sells']:
            prev_buys = [b for b in stats['buys'] if b['block'] < sell['block']]
            if prev_buys:
                latest_buy = max(prev_buys, key=lambda x: x['block'])
                hold_time = sell['block'] - latest_buy['block']
                total_hold_blocks += hold_time
                pairs += 1
        
        if pairs > 0:
            avg_hold = total_hold_blocks / pairs
            if avg_hold < MAX_AVG_HOLD_BLOCKS:
                reasons.append(f"RAPID_TRADING (avg:{int(avg_hold)}blk)")
        
        # Pattern 3: High frequency
        block_range = stats['trades'][-1]['block'] - stats['first_seen']
        if block_range > 0:
            trades_per_hour = (len(stats['trades']) / block_range) * 1200
            if trades_per_hour > MAX_TRADES_PER_HOUR:
                reasons.append(f"HIGH_FREQ ({trades_per_hour:.1f}/hr)")
        
        # Pattern 4: Same-block trading
        for i in range(len(stats['trades']) - 1):
            if (stats['trades'][i]['block'] == stats['trades'][i+1]['block'] and
                stats['trades'][i]['type'] != stats['trades'][i+1]['type']):
                reasons.append("SAME_BLOCK_TRADE")
                break
        
        if len(reasons) >= 2:
            print(f"\n🚨 BOT DETECTED: {address}")
            for r in reasons:
                print(f"   └─ {r}")
            self.blacklist_address(address, " | ".join(reasons))
    
    def blacklist_address(self, address, reason):
        """Submit blacklist transaction to smart contract"""
        try:
            is_blacklisted = self.contract.functions.isBlacklisted(address).call()
            if is_blacklisted:
                print(f"   ⚠️  Already blacklisted on-chain")
                self.blacklisted.add(address)
                return
            
            print(f"   📝 Submitting blacklist transaction...")
            
            tx = self.contract.functions.blacklistAddress(
                Web3.to_checksum_address(address),
                reason[:100]
            ).build_transaction({
                'from': self.account.address,
                'gas': 150000,
                'gasPrice': self.w3.eth.gas_price,
                'nonce': self.w3.eth.get_transaction_count(self.account.address)
            })
            
            signed_tx = self.w3.eth.account.sign_transaction(tx, self.account.key)
            tx_hash = self.w3.eth.send_raw_transaction(signed_tx.rawTransaction)
            
            print(f"   ⏳ TX: {tx_hash.hex()}")
            
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)
            
            if receipt['status'] == 1:
                print(f"   ✅ BLACKLISTED SUCCESSFULLY\n")
                self.blacklisted.add(address)
                
                with open('blacklisted.log', 'a') as f:
                    timestamp = datetime.utcnow().isoformat()
                    f.write(f"[{timestamp}] {address} | {reason} | TX:{tx_hash.hex()}\n")
            else:
                print(f"   ❌ Transaction failed\n")
                
        except Exception as e:
            print(f"   ❌ Error: {str(e)}\n")
    
    def run(self):
        """Main execution"""
        print(f"🕐 RUN START: {datetime.utcnow().isoformat()} UTC\n")
        
        self.scan_recent_blocks()
        self.save_state()
        
        print(f"\n📊 SUMMARY:")
        print(f"   Addresses Tracked: {len(self.trader_stats)}")
        print(f"   Bots Blacklisted: {len(self.blacklisted)}")
        print(f"   Last Block: {self.last_block}")
        print(f"\n✅ HYPERION GUARD - RUN COMPLETE\n")

if __name__ == '__main__':
    try:
        guard = HyperionGuard()
        guard.run()
    except Exception as e:
        print(f"\n❌ FATAL ERROR: {e}\n")
        raise
