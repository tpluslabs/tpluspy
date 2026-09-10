// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// Ondo Global Markets `SyntheticSharesOracle`, reduced to the fields a rate read consumes.
contract MockOndoSharesOracle {
    uint128 private shareValue;
    uint128 private pendingShareValue;
    uint256 private pauseStartTime;

    function setShareValue(uint128 value, uint128 pending, uint256 pauseAt) external {
        shareValue = value;
        pendingShareValue = pending;
        pauseStartTime = pauseAt;
    }

    function assetData(address)
        external
        view
        returns (uint128, uint128, uint256, uint256, uint16, uint48)
    {
        return (shareValue, pendingShareValue, 0, pauseStartTime, 0, 0);
    }
}

/// xStocks V2 `BackedAutoFeeTokenImplementation`: the ERC20 a holder deposits, carrying the
/// multiplier its rate is read from.
contract MockBackedAutoFeeToken {
    string public name;
    string public symbol;
    uint8 public constant decimals = 18;
    uint256 public totalSupply;
    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;

    bool private paused;
    uint256 private lastMultiplierValue;
    uint256 private nextMultiplier;
    uint256 private activationTime;
    uint256 private feeAppliedAt;
    uint256 private periodFee;
    uint256 private period;

    event Transfer(address indexed from, address indexed to, uint256 value);
    event Approval(address indexed owner, address indexed spender, uint256 value);

    constructor(string memory name_, string memory symbol_) {
        name = name_;
        symbol = symbol_;
    }

    function setMultiplier(
        uint256 current,
        uint256 next,
        uint256 activatesAt,
        uint256 lastFeeApplied,
        uint256 feePerPeriod_,
        uint256 periodLength_
    ) external {
        lastMultiplierValue = current;
        nextMultiplier = next;
        activationTime = activatesAt;
        feeAppliedAt = lastFeeApplied;
        periodFee = feePerPeriod_;
        period = periodLength_;
    }

    function setPaused(bool value) external {
        paused = value;
    }

    function isPaused() external view returns (bool) {
        return paused;
    }

    /// Mirrors the deployed token: the scheduled multiplier holds off until its activation, and
    /// the live one decays by every whole fee period since the fee was last applied.
    function getCurrentMultiplier() external view returns (uint256, uint256, uint256) {
        if (block.timestamp < activationTime) {
            return (lastMultiplierValue, 0, 0);
        }

        uint256 periodsPassed = (block.timestamp - feeAppliedAt) / period;
        uint256 current = nextMultiplier;
        if (periodFee > 0) {
            for (uint256 index = 0; index < periodsPassed; index++) {
                current = (current * (1e18 - periodFee)) / 1e18;
            }
        }
        return (current, periodsPassed, 0);
    }

    function newMultiplier() external view returns (uint256) {
        return nextMultiplier;
    }

    function newMultiplierActivationTime() external view returns (uint256) {
        return activationTime;
    }

    function lastTimeFeeApplied() external view returns (uint256) {
        return feeAppliedAt;
    }

    function feePerPeriod() external view returns (uint256) {
        return periodFee;
    }

    function periodLength() external view returns (uint256) {
        return period;
    }

    function mint(address to, uint256 amount) external {
        balanceOf[to] += amount;
        totalSupply += amount;
        emit Transfer(address(0), to, amount);
    }

    function approve(address spender, uint256 amount) external returns (bool) {
        allowance[msg.sender][spender] = amount;
        emit Approval(msg.sender, spender, amount);
        return true;
    }

    function transfer(address to, uint256 amount) external returns (bool) {
        balanceOf[msg.sender] -= amount;
        balanceOf[to] += amount;
        emit Transfer(msg.sender, to, amount);
        return true;
    }

    function transferFrom(address from, address to, uint256 amount) external returns (bool) {
        uint256 allowed = allowance[from][msg.sender];
        if (allowed != type(uint256).max) {
            allowance[from][msg.sender] = allowed - amount;
        }
        balanceOf[from] -= amount;
        balanceOf[to] += amount;
        emit Transfer(from, to, amount);
        return true;
    }
}
