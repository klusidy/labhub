/* eslint-disable @typescript-eslint/no-explicit-any */
declare module 'plotly.js-dist-min' {
  const Plotly: {
    newPlot(
      root: string | HTMLElement,
      data: any[],
      layout?: any,
      config?: any
    ): Promise<any>;
    react(
      root: string | HTMLElement,
      data: any[],
      layout?: any,
      config?: any
    ): Promise<any>;
    purge(root: string | HTMLElement): void;
  };

  export default Plotly;
}
