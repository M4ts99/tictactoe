# =============================================================================
# robot/positions.py – Feste Roboter-Koordinaten (nach Teach-In befuellen)
# =============================================================================

# Spielfeld-Positionen (x, y, z) in mm
FIELD_POSITIONS = {
    1: (0.0, 0.0, 0.0),   # Oben links
    2: (0.0, 0.0, 0.0),   # Oben mitte
    3: (0.0, 0.0, 0.0),   # Oben rechts
    4: (0.0, 0.0, 0.0),   # Mitte links
    5: (0.0, 0.0, 0.0),   # Mitte
    6: (0.0, 0.0, 0.0),   # Mitte rechts
    7: (0.0, 0.0, 0.0),   # Unten links
    8: (0.0, 0.0, 0.0),   # Unten mitte
    9: (0.0, 0.0, 0.0),   # Unten rechts
}

STORAGE_X  = (0.0, 0.0, 0.0)   # Lager X-Steine
STORAGE_O  = (0.0, 0.0, 0.0)   # Lager O-Steine
REWARD_POS = (0.0, 0.0, 0.0)   # Rutsche
