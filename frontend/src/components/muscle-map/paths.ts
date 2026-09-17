/**
 * Silhouette traced by hand, right half only: every shape is drawn once for the
 * viewer's right side and mirrored across the body axis (x = 100).
 *
 * viewBox is 0 0 200 400. Muscle shapes stay inside the body outline so the
 * figure still reads as a body when every region is cold.
 */

export type View = 'front' | 'back';

/** Mirror across x = 100, for the left-side copy of a shape. */
export const MIRROR = 'matrix(-1 0 0 1 200 0)';

/** Torso is drawn whole (no seam down the middle); arms and legs are mirrored. */
export const BODY: Record<View, { full: string[]; half: string[] }> = {
  front: { full: ['M 100 66 L 112 68 C 126 72 136 78 140 92 L 136 120 L 128 160 L 126 186 L 132 206 L 128 220 L 72 220 L 68 206 L 74 186 L 72 160 L 64 120 L 60 92 C 64 78 74 72 88 68 Z'], half: ['M 140 92 C 150 96 152 104 151 116 L 147 158 L 150 200 L 152 214 L 140 216 L 138 200 L 136 158 L 132 120 C 132 104 134 96 140 92 Z', 'M 102 222 L 128 218 C 134 250 132 270 128 296 L 124 330 L 122 372 L 120 388 L 106 388 L 106 340 L 105 300 L 102 262 Z'] },
  back: { full: ['M 100 66 L 112 68 C 126 72 136 78 140 92 L 136 120 L 128 160 L 126 186 L 132 206 L 128 220 L 72 220 L 68 206 L 74 186 L 72 160 L 64 120 L 60 92 C 64 78 74 72 88 68 Z'], half: ['M 140 92 C 150 96 152 104 151 116 L 147 158 L 150 200 L 152 214 L 140 216 L 138 200 L 136 158 L 132 120 C 132 104 134 96 140 92 Z', 'M 102 222 L 128 218 C 134 250 132 270 128 296 L 124 330 L 122 372 L 120 388 L 106 388 L 106 340 L 105 300 L 102 262 Z'] },
};

export interface MuscleShape {
  muscle: string;
  view: View;
  d: string;
}

/** Draw order matters: later shapes paint over earlier ones. */
export const SHAPES: MuscleShape[] = [
  // ── front ───────────────────────────────────────────────
  { muscle: 'traps', view: 'front', d: 'M 100 67 L 113 70 L 120 81 L 100 83 Z' },
  { muscle: 'side_delts', view: 'front', d: 'M 133 90 C 145 94 148 104 146 118 L 138 116 C 139 104 136 96 131 93 Z' },
  { muscle: 'front_delts', view: 'front', d: 'M 118 78 C 130 80 138 86 139 98 L 130 104 C 128 92 122 84 115 82 Z' },
  { muscle: 'chest', view: 'front', d: 'M 103 90 L 122 87 C 132 92 134 102 132 113 C 121 120 110 121 103 119 Z' },
  { muscle: 'biceps', view: 'front', d: 'M 134 118 C 141 121 144 130 143 142 L 140 158 L 133 156 L 132 133 Z' },
  { muscle: 'forearms', view: 'front', d: 'M 137 165 C 145 172 148 185 148 201 L 147 211 L 138 210 L 135 190 Z' },
  { muscle: 'abs', view: 'front', d: 'M 102 127 L 113 129 C 115 150 113 170 111 186 L 102 187 Z' },
  { muscle: 'obliques', view: 'front', d: 'M 114 131 C 123 141 123 160 119 181 L 112 183 C 114 165 115 147 114 131 Z' },
  { muscle: 'hip_flexors', view: 'front', d: 'M 102 190 L 118 187 L 123 206 L 104 209 Z' },
  { muscle: 'adductors', view: 'front', d: 'M 103 224 L 113 223 C 114 246 112 264 108 276 L 103 274 Z' },
  { muscle: 'quads', view: 'front', d: 'M 106 224 L 126 220 C 131 248 129 272 124 292 L 109 292 C 105 268 104 244 106 224 Z' },
  { muscle: 'tibialis', view: 'front', d: 'M 108 304 C 118 302 121 320 120 348 L 116 372 L 110 370 C 108 344 107 322 108 304 Z' },

  // ── back ────────────────────────────────────────────────
  { muscle: 'traps', view: 'back', d: 'M 100 67 L 113 70 C 123 80 124 96 120 112 L 100 116 Z' },
  { muscle: 'rear_delts', view: 'back', d: 'M 119 78 C 132 82 140 88 140 100 L 130 106 C 128 94 124 84 116 81 Z' },
  { muscle: 'rhomboids', view: 'back', d: 'M 101 99 L 115 103 L 113 128 L 101 130 Z' },
  { muscle: 'lats', view: 'back', d: 'M 116 112 C 126 121 129 136 127 152 L 116 174 L 107 168 C 110 148 112 129 116 112 Z' },
  { muscle: 'triceps', view: 'back', d: 'M 133 114 C 142 118 145 129 144 143 L 140 158 L 133 156 L 131 131 Z' },
  { muscle: 'forearms', view: 'back', d: 'M 137 165 C 145 172 148 185 148 201 L 147 211 L 138 210 L 135 190 Z' },
  { muscle: 'lower_back', view: 'back', d: 'M 101 138 L 112 141 C 115 159 115 176 114 188 L 101 189 Z' },
  { muscle: 'glutes', view: 'back', d: 'M 101 194 C 114 191 125 198 128 209 C 129 224 120 234 108 235 L 101 234 Z' },
  { muscle: 'hamstrings', view: 'back', d: 'M 107 248 L 127 244 C 130 268 127 288 122 300 L 109 300 C 105 278 105 262 107 248 Z' },
  { muscle: 'calves', view: 'back', d: 'M 107 310 C 120 308 125 326 123 346 C 121 364 115 372 110 370 C 106 350 105 326 107 310 Z' },
];

export const VIEW_LABEL: Record<View, string> = { front: 'Face', back: 'Dos' };
