'use strict';

/** One-shot settlement gate for asynchronous child-process lifecycles. */
function createSettlement(resolve) {
    let settled = false;
    return {
        settle(value) {
            if (settled) return false;
            settled = true;
            resolve(value);
            return true;
        },
        isSettled() {
            return settled;
        },
    };
}

module.exports = { createSettlement };
