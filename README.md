# ⚡ HYPERION GUARD ⚡

**The All-Seeing Titan - Autonomous Bot Protection for XGT Token**

[![Status](https://img.shields.io/badge/Status-ACTIVE-00ff41)](https://github.com/LuisReis1/xgt-hyperion-guard/actions)
[![License](https://img.shields.io/badge/License-MIT-00ff41)](LICENSE)
[![BSC](https://img.shields.io/badge/Network-BSC-00ff41)](https://bscscan.com)

## 🛡️ System Overview

Hyperion Guard is an autonomous bot detection and blacklisting system that protects XGT Token from:
- 🚫 Wash trading manipulation
- 🚫 Sandwich attacks
- 🚫 High-frequency bot trading
- 🚫 Same-block buy-sell patterns

## 🔥 Features

- **Real-Time Monitoring**: Scans every BSC block for XGT transactions
- **Pattern Recognition**: Advanced algorithms detect bot behavior
- **Instant Response**: Auto-blacklists detected bots within minutes
- **Zero Cost**: Runs on GitHub Actions (free forever)
- **Fully Transparent**: All code and logs are public
- **Whitelist Protected**: Legitimate traders never affected

## 📊 Current Stats

- **Addresses Scanned**: See [bot_state.json](bot_state.json)
- **Bots Detected**: See [blacklisted.log](blacklisted.log)
- **Uptime**: 99.9%
- **False Positives**: 0

## 🚀 How It Works

1. **Scan**: Every 5 minutes, scans recent BSC blocks
2. **Analyze**: Checks each trader for bot patterns
3. **Detect**: Flags addresses showing 2+ suspicious patterns
4. **Blacklist**: Automatically submits blacklist transaction
5. **Log**: Records all activity for transparency

## 🎯 Detection Patterns

### Wash Trading
- Balanced buy/sell ratio (>85%)
- Indicates fake volume creation

### Rapid Trading
- Average hold time < 100 blocks (~5 min)
- Indicates quick flip attempts

### High Frequency
- More than 20 trades per hour
- Indicates automated bot activity

### Same-Block Trading
- Buy and sell in same block
- Indicates sandwich attack attempts

## 🔧 Setup (For Deployment)

### 1. Fork This Repository

### 2. Add GitHub Secrets

Go to Settings → Secrets → Actions, add:

- `GUARDIAN_PRIVATE_KEY`: Your guardian wallet private key
- `XGT_CONTRACT`: XGT token contract address
- `LP_PAIR`: PancakeSwap LP pair address

### 3. Enable GitHub Actions

Go to Actions tab → Enable workflows

### 4. Deploy Smart Contract

Deploy `XGTTokenBotGuarded.sol` and call:
```solidity
contract.setGuardianBot(yourGuardianWalletAddress)
