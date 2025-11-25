// SPDX-License-Identifier: MIT
pragma solidity 0.8.19;

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/security/ReentrancyGuard.sol";

/**
 * @title XGT Token - Hyperion Guard Protected
 * @notice Carbon-backed cryptocurrency with autonomous bot protection
 */
contract XGTTokenBotGuarded is ERC20, Ownable, ReentrancyGuard {
    
    uint256 public constant TOTAL_SUPPLY = 80_000_000_000 * 10**18;
    uint256 public constant MINING_ALLOCATION = TOTAL_SUPPLY / 2;
    uint256 public constant DEVELOPMENT_ALLOCATION = TOTAL_SUPPLY / 2;
    uint256 public constant MINING_DURATION = 1460 days;
    
    uint256 public miningStart;
    uint256 public miningTokensDistributed;
    address public miningDistributor;
    address public developmentWallet;
    address public liquidityPool;
    address public guardianBot;
    
    mapping(address => bool) public isBlacklisted;
    mapping(address => bool) public isWhitelisted;
    
    event Blacklisted(address indexed account, string reason);
    event Whitelisted(address indexed account);
    event GuardianBotSet(address indexed bot);
    event MiningRewardsDistributed(address indexed recipient, uint256 amount);
    
    constructor(address _developmentWallet) ERC20("XGT Token", "XGT") {
        require(_developmentWallet != address(0), "Invalid development wallet");
        
        developmentWallet = _developmentWallet;
        miningStart = block.timestamp;
        
        isWhitelisted[msg.sender] = true;
        isWhitelisted[_developmentWallet] = true;
        isWhitelisted[address(this)] = true;
        
        _mint(address(this), MINING_ALLOCATION);
        _mint(_developmentWallet, DEVELOPMENT_ALLOCATION);
    }
    
    function setGuardianBot(address _bot) external onlyOwner {
        require(_bot != address(0), "Invalid bot address");
        guardianBot = _bot;
        emit GuardianBotSet(_bot);
    }
    
    function blacklistAddress(address account, string memory reason) external {
        require(msg.sender == guardianBot || msg.sender == owner(), "Only guardian or owner");
        require(!isWhitelisted[account], "Cannot blacklist whitelisted address");
        isBlacklisted[account] = true;
        emit Blacklisted(account, reason);
    }
    
    function whitelistAddress(address account, bool status) external onlyOwner {
        isWhitelisted[account] = status;
        if (status) {
            isBlacklisted[account] = false;
            emit Whitelisted(account);
        }
    }
    
    function removeBlacklist(address account) external onlyOwner {
        isBlacklisted[account] = false;
    }
    
    function setLiquidityPool(address _pool) external onlyOwner {
        liquidityPool = _pool;
        isWhitelisted[_pool] = true;
    }
    
    function setMiningDistributor(address _distributor) external onlyOwner {
        miningDistributor = _distributor;
        isWhitelisted[_distributor] = true;
    }
    
    function distributeMiningRewards(address recipient, uint256 amount) external nonReentrant {
        require(msg.sender == miningDistributor, "Only mining distributor");
        require(recipient != address(0), "Invalid recipient");
        require(amount > 0, "Amount must be positive");
        
        uint256 elapsedTime = block.timestamp - miningStart;
        uint256 maxMineable = (MINING_ALLOCATION * elapsedTime) / MINING_DURATION;
        require(miningTokensDistributed + amount <= maxMineable, "Exceeds mining schedule");
        require(balanceOf(address(this)) >= amount, "Insufficient mining balance");
        
        miningTokensDistributed += amount;
        _transfer(address(this), recipient, amount);
        
        emit MiningRewardsDistributed(recipient, amount);
    }
    
    function _transfer(address sender, address recipient, uint256 amount) 
        internal virtual override nonReentrant {
        
        require(sender != address(0), "Transfer from zero");
        require(recipient != address(0), "Transfer to zero");
        require(amount > 0, "Amount must be positive");
        require(!isBlacklisted[sender], "Sender is blacklisted");
        require(!isBlacklisted[recipient], "Recipient is blacklisted");
        
        super._transfer(sender, recipient, amount);
    }
    
    function getRemainingMiningAllocation() external view returns (uint256) {
        return balanceOf(address(this));
    }
    
    function recoverERC20(address token, uint256 amount) external onlyOwner {
        require(token != address(this), "Cannot recover XGT");
        IERC20(token).transfer(owner(), amount);
    }
}
