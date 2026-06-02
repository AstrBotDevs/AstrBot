import { VNodeChild } from 'vue';
declare module '@vue/runtime-dom' {
  export interface HTMLAttributes {
    $children?: VNodeChild;
  }
  export interface SVGAttributes {
    $children?: VNodeChild;
    strokeWidth?: string | number;
  }
}
