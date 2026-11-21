export const ROLES={admin:'印刷主管',pressman:'机长',viewer:'只读观察员'};
export const DEFECTS=['合格','乳化','偏色'];
export const STATES={hold:'量产停机',setup:'待开机',adjusting:'调机复验中',production:'已签印量产',issued:'指令待执行',executed:'已执行待复验',signed:'复验闭合',unmeasured:'未判读',classifying:'判读中',classified:'已判读',failed:'判读失败'};
export const CHECKOUT_STATES={active:'领单生效待补传',conflicted:'补传冲突待核对',reconciled:'已核对关闭'};
export const RECORD_STATES={pending:'本机待补传',applied:'已补传落地',conflicted:'冲突留档待核对'};
export const OP_LABELS={proof:'离线样张',classify:'离线判读',reproof:'离线复验判读',adjustment:'离线调机',instruction:'离线修订指令',execute:'离线登记执行'};
