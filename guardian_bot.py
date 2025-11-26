#!/usr/bin/env python3
"""
HYPERION GUARD - Autonomous Bot Detection System (Monitor Mode)
Monitors XGT token transactions and logs wash trading bots
"""

import os
import json
from datetime import datetime
from web3 import Web3
from collections import defaultdict

# Configuration
BSC_RPC = os.environ.get('BSC_RPC', 'https://bsc-dataseed.binance.org/')
XGT_CONTRACT = os.environ.get('XGT_CONTRACT', '0x654E38A4516F5476D723D770382A5EaF8Bae0e0D')
LP_PAIR = os.environ.get('LP_PAIR', '0x90868821cb533f54b90bbdd5ff4128a13e0376ff')

# Detection thresholds
MIN_TRADES_TO_FLAG = 8
MAX_AVG_HOLD_BLOCKS = 100
WASH_TRADING_THRESHOLD = 0.85
MAX_TRADES_PER_HOUR = 20

# Minimal ABI for Transfer events
CONTRACT_ABI = [{
    "anonymous": False,
    "inputs": [
        {"indexed": True, "type": "address", "name": "from"},
        {"indexed": True, "type": "address", "name": "to"},
        {"indexed": False, "type": "uint256", "name": "value"}
    ],
    "name": "Transfer",
    "type": "event"
}]

class HyperionGuard:
    def __init__(self):
        print("=" * 70)
        print("🛡️  HYPERION GUARD - AUTONOMOUS BOT DETECTION SYSTEM")
        print("=" * 70)
        print("MODE: MONITOR & LOG (No Auto-Blacklist)")
        print("=" * 70)
        
        self.w3 = Web3(Web3.HTTPProvider(BSC_RPC))
        if not self.w3.is_connected():
            raise Exception("❌ Failed to connect to BSC RPC")
        
        print(f"✅ Connected to BSC (Block: {self.w3.eth.block_number})")
        
        self.contract = self.w3.eth.contract(
            address=Web3.to_checksum_address(XGT_CONTRACT),
            abi=CONTRACT_ABI
        )
        
        print(f"✅ XGT Contract: {XGT_CONTRACT}")
        print(f"✅ Monitoring: ALL XGT transfers (not limited to specific pairs)")
        
        self.load_state()
        print(f"✅ Loaded state (Last block: {self.last_block})")
        print("=" * 70 + "\n")
        
    def load_state(self):
        """Load tracking data from previous runs"""
        try:
            with open('bot_state.json', 'r') as f:
                data = json.load(f)
                self.last_block = data.get('last_block', self.w3.eth.block_number - 50)
                self.trader_stats = defaultdict(
                    lambda: {'buys': [], 'sells': [], 'trades': [], 'first_seen': 0},
                    {k: v for k, v in data.get('trader_stats', {}).items()}
                )
                self.detected_bots = set(data.get('detected_bots', []))
        except FileNotFoundError:
            print("⚠️  No previous state found, starting fresh")
            self.last_block = self.w3.eth.block_number - 50
            self.trader_stats = defaultdict(lambda: {
                'buys': [], 'sells': [], 'trades': [], 'first_seen': 0
            })
            self.detected_bots = set()
    
    def save_state(self):
        """Save tracking data for next run"""
        with open('bot_state.json', 'w') as f:
            json.dump({
                'last_block': self.last_block,
                'last_update': datetime.utcnow().isoformat(),
                'trader_stats': {k: v for k, v in self.trader_stats.items()},
                'detected_bots': list(self.detected_bots),
                'total_scanned': len(self.trader_stats),
                'total_detected': len(self.detected_bots)
            }, f, indent=2)
    
    def scan_recent_blocks(self):
        """Scan recent blocks for XGT transfers"""
        current_block = self.w3.eth.block_number
        MAX_BLOCK_SPAN = 50  # XGT has very high activity - keep it small
        from_block = max(self.last_block + 1, current_block - MAX_BLOCK_SPAN)
        
        # SAFETY: Never scan more than MAX_BLOCK_SPAN blocks in one run
        if (current_block - from_block) > MAX_BLOCK_SPAN:
            from_block = current_block - MAX_BLOCK_SPAN
        
        print(f"🔍 Scanning blocks {from_block} → {current_block}...")
        
        try:
            events = self.contract.events.Transfer.get_logs(
                from_block=from_block,
                to_block=current_block
            )
            
            print(f"📊 Found {len(events)} transfers\n")
            
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
        
        # Skip zero address (mints/burns)
        zero_addr = '0x0000000000000000000000000000000000000000'
        if from_addr == zero_addr or to_addr == zero_addr:
            return
        
        # Track BOTH sender and receiver for comprehensive monitoring
        for trader in [from_addr, to_addr]:
            if trader not in self.trader_stats:
                self.trader_stats[trader] = {
                    'buys': [], 'sells': [], 'trades': [], 'first_seen': block_num
                }
            
            stats = self.trader_stats[trader]
            
            # Determine if this is a buy or sell (relative to the trader)
            is_sender = (trader == from_addr)
            trade = {
                'type': 'send' if is_sender else 'receive',
                'block': block_num,
                'amount': str(amount),
                'counterparty': to_addr if is_sender else from_addr
            }
            
            stats['trades'].append(trade)
            if is_sender:
                stats['sells'].append(trade)
            else:
                stats['buys'].append(trade)
            
            if len(stats['trades']) >= MIN_TRADES_TO_FLAG:
                self.check_bot_pattern(trader, stats)
    
    def check_bot_pattern(self, address, stats):
        """Detect bot trading patterns"""
        if address in self.detected_bots:
            return
        
        reasons = []
        
        # Pattern 1: Wash trading
        buy_count = len(stats['buys'])
        sell_count = len(stats['sells'])
        if buy_count > 0 and sell_count > 0:
            wash_ratio = min(buy_count, sell_count) / max(buy_count, sell_count)
            if wash_ratio >= WASH_TRADING_THRESHOLD:
                reasons.append(f"WASH_TRADING ({buy_count}B/{sell_count}S, ratio:{wash_ratio:.2f})")
        
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
                reasons.append(f"RAPID_TRADING (avg_hold:{int(avg_hold)}blk={int(avg_hold*3/60)}min)")
        
        # Pattern 3: High frequency
        block_range = stats['trades'][-1]['block'] - stats['first_seen']
        if block_range > 0:
            trades_per_hour = (len(stats['trades']) / block_range) * 1200
            if trades_per_hour > MAX_TRADES_PER_HOUR:
                reasons.append(f"HIGH_FREQUENCY ({trades_per_hour:.1f}trades/hr)")
        
        # Pattern 4: Same-block trading
        for i in range(len(stats['trades']) - 1):
            if (stats['trades'][i]['block'] == stats['trades'][i+1]['block'] and
                stats['trades'][i]['type'] != stats['trades'][i+1]['type']):
                reasons.append("SAME_BLOCK_BUY_SELL")
                break
        
        if len(reasons) >= 2:
            self.log_bot_detection(address, reasons, stats)
    
    def log_bot_detection(self, address, reasons, stats):
        """Log detected bot to file"""
        print(f"\n{'='*70}")
        print(f"🚨 BOT DETECTED: {address}")
        print(f"{'='*70}")
        for r in reasons:
            print(f"   ⚠️  {r}")
        print(f"   📊 Total Trades: {len(stats['trades'])} ({len(stats['buys'])} buys, {len(stats['sells'])} sells)")
        print(f"   🕐 First Seen: Block {stats['first_seen']}")
        print(f"{'='*70}\n")
        
        self.detected_bots.add(address)
        
        # Log to file
        with open('blacklisted.log', 'a') as f:
            timestamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')
            reason_str = " | ".join(reasons)
            f.write(f"[{timestamp}] 🚨 BOT: {address}\n")
            f.write(f"           PATTERNS: {reason_str}\n")
            f.write(f"           STATS: {len(stats['trades'])} trades ({len(stats['buys'])}B/{len(stats['sells'])}S)\n")
            f.write(f"           ACTION: LOGGED (Manual review recommended)\n")
            f.write(f"{'-'*70}\n")
    
    def run(self):
        """Main execution"""
        start_time = datetime.utcnow()
        print(f"🕐 RUN START: {start_time.isoformat()} UTC\n")
        
        self.scan_recent_blocks()
        self.save_state()
        
        end_time = datetime.utcnow()
        duration = (end_time - start_time).total_seconds()
        
        print(f"\n{'='*70}")
        print(f"📊 SCAN SUMMARY")
        print(f"{'='*70}")
        print(f"   Addresses Tracked: {len(self.trader_stats)}")
        print(f"   Bots Detected: {len(self.detected_bots)}")
        print(f"   Last Block Scanned: {self.last_block}")
        print(f"   Scan Duration: {duration:.2f} seconds")
        print(f"   Next Scan: ~5 minutes")
        print(f"{'='*70}")
        print(f"\n✅ HYPERION GUARD - SCAN COMPLETE\n")

if __name__ == '__main__':
    try:
        guard = HyperionGuard()
        guard.run()
    except Exception as e:
        print(f"\n❌ FATAL ERROR: {e}\n")
        import traceback
        traceback.print_exc()
        raise
