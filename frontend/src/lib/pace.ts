let light = false;
const listeners = new Set<(value: boolean) => void>();

export function isPanelLight() {
  return light;
}

export function setPanelLight(value: boolean) {
  light = value;
  listeners.forEach((listen) => listen(value));
}

export function watchPanelLight(listen: (value: boolean) => void) {
  listeners.add(listen);
  return () => listeners.delete(listen);
}
