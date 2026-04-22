// RTL Half Adder — synthesize with Yosys to get gate-level netlist
// Run: yosys -p "synth -top half_adder; write_verilog -noattr half_adder_synth.v" half_adder_rtl.v
module half_adder (
    input  a,
    input  b,
    output sum,
    output carry
);
    assign sum   = a ^ b;
    assign carry = a & b;
endmodule
