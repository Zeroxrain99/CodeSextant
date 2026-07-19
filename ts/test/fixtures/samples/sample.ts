export function helper(): number {
  return 1;
}

export class Service {
  run(): void {}
}

export abstract class Base {
  abstract handle(): void;
}

export interface Shape {
  area(): number;
}

export type ID = string;

export enum Color {
  Red,
  Green,
}

const version = "1.0";
