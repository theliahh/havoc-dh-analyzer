"""Hero tree detection for Havoc DH.

From talents: WCL talent entry IDs of the hero-tree nodes, derived on 2026-10-22 (patch 12.1.5)
by comparing top logs whose tree was confirmed from casts. From events: signature abilities.
"""
AR_TALENTS = {117492, 117494, 117495, 117500, 117503, 117511, 117512, 117516}
FS_TALENTS = {117498, 117501, 117502, 117506, 117509, 117513, 117514, 117515}
AR_ABILITIES = {"Reaver's Glaive", "Art of the Glaive"}
FS_ABILITIES = {"Demonsurge", "Abyssal Gaze", "Consuming Fire"}


def from_talents(talent_ids):
    t = set(talent_ids)
    a, f = len(t & AR_TALENTS), len(t & FS_TALENTS)
    if a >= 5 and not f:
        return "AR"
    if f >= 5 and not a:
        return "FS"
    return None


def from_ability_names(names):
    names = set(names)
    ar, fs = bool(names & AR_ABILITIES), bool(names & FS_ABILITIES)
    return "AR" if ar and not fs else "FS" if fs and not ar else None
