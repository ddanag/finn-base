import numpy as np
from onnx import TensorProto, helper

import finn.core.onnx_exec as oxe
from finn.core.datatype import DataType
from finn.core.modelwrapper import ModelWrapper
from finn.custom_op.general.im2col import compute_conv_output_dim
from finn.transformation.infer_datatypes import InferDataTypes
from finn.transformation.infer_shapes import InferShapes


def check_two_dict_for_equality(dict1, dict2):
    for key in dict1:
        assert key in dict2, "Key: {} is not in both dictionaries".format(key)
        assert (
            dict1[key] == dict2[key]
        ), """Values for key {} are not the same
        in both dictionaries""".format(
            key
        )

    return True


def execution_im2col(
    x,
    idt,
    k_h,
    k_w,
    stride,
    ifm_ch,
    ifm_dim_h,
    ifm_dim_w,
    pad_amt,
    pad_val=0,
    dilation=1,
):
    pad_amt_h = pad_amt[0] + pad_amt[2]
    pad_amt_w = pad_amt[1] + pad_amt[3]
    ofm_dim_h = compute_conv_output_dim(ifm_dim_h, k_h, stride, pad_amt_h, dilation)
    ofm_dim_w = compute_conv_output_dim(ifm_dim_w, k_w, stride, pad_amt_w, dilation)

    # set up onnx model
    inp = helper.make_tensor_value_info(
        "inp", TensorProto.FLOAT, [1, ifm_dim_h, ifm_dim_w, ifm_ch]
    )
    outp = helper.make_tensor_value_info(
        "outp", TensorProto.FLOAT, [1, ofm_dim_h, ofm_dim_w, k_h * k_w * ifm_ch]
    )

    im2col_node = helper.make_node(
        "Im2Col",
        ["inp"],
        ["outp"],
        domain="finn.custom_op.general",
        stride=stride,
        kernel_size=[k_h, k_w],
        pad_amount=pad_amt,
        pad_value=pad_val,
        input_shape="(1,{},{},{})".format(ifm_dim_h, ifm_dim_w, ifm_ch),
        dilations=dilation,
    )

    graph = helper.make_graph(
        nodes=[im2col_node], name="im2col_graph", inputs=[inp], outputs=[outp]
    )

    model = helper.make_model(graph, producer_name="im2col-model")
    model = ModelWrapper(model)

    model.set_tensor_datatype("inp", idt)

    # test shape inference
    model.transform(InferShapes())
    assert model.get_tensor_shape("outp") == [
        1,
        ofm_dim_h,
        ofm_dim_w,
        k_h * k_w * ifm_ch,
    ]

    # test datatype inference
    assert model.get_tensor_datatype("outp") is DataType.FLOAT32
    model = model.transform(InferDataTypes())
    assert model.get_tensor_datatype("outp") is idt

    # prepare input data
    input_dict = {"inp": x}

    # execute model
    y_produced = oxe.execute_onnx(model, input_dict)["outp"]

    return y_produced


# Configurations tested:
# case id     | 0       | 1    | 2    | 3    | 4    | 5    | 6    | 7    | 8    | 9    |
# idt         | Bipolar | INT8 | INT8 | INT8 | INT8 | INT8 | INT8 | INT8 | INT8 | INT8 |
# ifm_dim_H   | 5       | 5    | 5    | 5    | 5    | 5    | 5    | 5    | 5    | 5    |
# ifm_dim_W   | 5       | 5    | 5    | 5    | 5    | 1    | 1    | 1    | 1    | 1    |
# ifm_ch      | 2       | 2    | 2    | 2    | 2    | 2    | 2    | 2    | 2    | 2    |
# pad_amt     | 0       | 0    | 1    | 1    | 1    | 0    | 0    | 1    | 1    | 1    |
# pad_val     | 0       | 0    | 0    | 0    | 0    | 0    | 0    | 0    | 0    | 0    |
# k_H         | 2       | 2    | 2    | 2    | 3    | 2    | 2    | 2    | 2    | 3    |
# k_W         | 2       | 2    | 2    | 2    | 3    | 1    | 1    | 1    | 1    | 1    |
# stride      | 1       | 1    | 1    | 2    | 2    | 1    | 1    | 1    | 2    | 2    |
# dilations   | 1       | 2    | 2    | 2    | 2    | 1    | 2    | 2    | 2    | 2    |
def test_im2col_dilations():
    case_id = 0
    idt = DataType.INT8
    k_H = 2
    k_W = 2
    stride = 1
    ifm_ch = 2
    ifm_dim_H = 5
    ifm_dim_W = 5
    pad_amt = [0, 0, 0, 0]
    pad_val = 0
    dilation = 1

    x = np.asarray(
        [
            [
                [[1, -1], [2, -2], [3, -3], [4, -4], [5, -5]],
                [[6, -6], [7, -7], [8, -8], [9, -9], [10, -10]],
                [[11, -11], [12, -12], [13, -13], [14, -14], [15, -15]],
                [[16, -16], [17, -17], [18, -18], [19, -19], [20, -20]],
                [[21, -21], [22, -22], [23, -23], [24, -24], [25, -25]],
            ]
        ],
        dtype=np.float32,
    )

    expected = np.asarray(
        [
            [
                [
                    [1, -1, 2, -2, 6, -6, 7, -7],
                    [2, -2, 3, -3, 7, -7, 8, -8],
                    [3, -3, 4, -4, 8, -8, 9, -9],
                    [4, -4, 5, -5, 9, -9, 10, -10],
                ],
                [
                    [6, -6, 7, -7, 11, -11, 12, -12],
                    [7, -7, 8, -8, 12, -12, 13, -13],
                    [8, -8, 9, -9, 13, -13, 14, -14],
                    [9, -9, 10, -10, 14, -14, 15, -15],
                ],
                [
                    [11, -11, 12, -12, 16, -16, 17, -17],
                    [12, -12, 13, -13, 17, -17, 18, -18],
                    [13, -13, 14, -14, 18, -18, 19, -19],
                    [14, -14, 15, -15, 19, -19, 20, -20],
                ],
                [
                    [16, -16, 17, -17, 21, -21, 22, -22],
                    [17, -17, 18, -18, 22, -22, 23, -23],
                    [18, -18, 19, -19, 23, -23, 24, -24],
                    [19, -19, 20, -20, 24, -24, 25, -25],
                ],
            ]
        ],
        dtype=np.float32,
    )

    produced = execution_im2col(
        x,
        idt,
        k_H,
        k_W,
        stride,
        ifm_ch,
        ifm_dim_H,
        ifm_dim_W,
        pad_amt,
        pad_val,
        dilation,
    )

    assert (produced == expected).all(), "Test failed for case number {}".format(
        case_id
    )

    case_id = 1
    idt = DataType.INT8
    k_H = 2
    k_W = 2
    stride = 1
    ifm_ch = 2
    ifm_dim_H = 5
    ifm_dim_W = 5
    pad_amt = [0, 0, 0, 0]
    pad_val = 0
    dilation = 2

    x = np.asarray(
        [
            [
                [[1, -1], [2, -2], [3, -3], [4, -4], [5, -5]],
                [[6, -6], [7, -7], [8, -8], [9, -9], [10, -10]],
                [[11, -11], [12, -12], [13, -13], [14, -14], [15, -15]],
                [[16, -16], [17, -17], [18, -18], [19, -19], [20, -20]],
                [[21, -21], [22, -22], [23, -23], [24, -24], [25, -25]],
            ]
        ],
        dtype=np.float32,
    )

    expected = np.asarray(
        [
            [
                [
                    [1, -1, 3, -3, 11, -11, 13, -13],
                    [2, -2, 4, -4, 12, -12, 14, -14],
                    [3, -3, 5, -5, 13, -13, 15, -15],
                ],
                [
                    [6, -6, 8, -8, 16, -16, 18, -18],
                    [7, -7, 9, -9, 17, -17, 19, -19],
                    [8, -8, 10, -10, 18, -18, 20, -20],
                ],
                [
                    [11, -11, 13, -13, 21, -21, 23, -23],
                    [12, -12, 14, -14, 22, -22, 24, -24],
                    [13, -13, 15, -15, 23, -23, 25, -25],
                ],
            ]
        ],
        dtype=np.float32,
    )

    produced = execution_im2col(
        x,
        idt,
        k_H,
        k_W,
        stride,
        ifm_ch,
        ifm_dim_H,
        ifm_dim_W,
        pad_amt,
        pad_val,
        dilation,
    )

    assert (produced == expected).all(), "Test failed for case number {}".format(
        case_id
    )

    case_id = 2
    idt = DataType.INT8
    k_H = 2
    k_W = 2
    stride = 1
    ifm_ch = 2
    ifm_dim_H = 5
    ifm_dim_W = 5
    pad_amt = [1, 1, 1, 1]
    pad_val = 0
    dilation = 2

    x = np.asarray(
        [
            [
                [[1, -1], [2, -2], [3, -3], [4, -4], [5, -5]],
                [[6, -6], [7, -7], [8, -8], [9, -9], [10, -10]],
                [[11, -11], [12, -12], [13, -13], [14, -14], [15, -15]],
                [[16, -16], [17, -17], [18, -18], [19, -19], [20, -20]],
                [[21, -21], [22, -22], [23, -23], [24, -24], [25, -25]],
            ]
        ],
        dtype=np.float32,
    )

    expected = np.asarray(
        [
            [
                [
                    [0, 0, 0, 0, 0, 0, 7, -7],
                    [0, 0, 0, 0, 6, -6, 8, -8],
                    [0, 0, 0, 0, 7, -7, 9, -9],
                    [0, 0, 0, 0, 8, -8, 10, -10],
                    [0, 0, 0, 0, 9, -9, 0, 0],
                ],
                [
                    [0, 0, 2, -2, 0, 0, 12, -12],
                    [1, -1, 3, -3, 11, -11, 13, -13],
                    [2, -2, 4, -4, 12, -12, 14, -14],
                    [3, -3, 5, -5, 13, -13, 15, -15],
                    [4, -4, 0, 0, 14, -14, 0, 0],
                ],
                [
                    [0, 0, 7, -7, 0, 0, 17, -17],
                    [6, -6, 8, -8, 16, -16, 18, -18],
                    [7, -7, 9, -9, 17, -17, 19, -19],
                    [8, -8, 10, -10, 18, -18, 20, -20],
                    [9, -9, 0, 0, 19, -19, 0, 0],
                ],
                [
                    [0, 0, 12, -12, 0, 0, 22, -22],
                    [11, -11, 13, -13, 21, -21, 23, -23],
                    [12, -12, 14, -14, 22, -22, 24, -24],
                    [13, -13, 15, -15, 23, -23, 25, -25],
                    [14, -14, 0, 0, 24, -24, 0, 0],
                ],
                [
                    [0, 0, 17, -17, 0, 0, 0, 0],
                    [16, -16, 18, -18, 0, 0, 0, 0],
                    [17, -17, 19, -19, 0, 0, 0, 0],
                    [18, -18, 20, -20, 0, 0, 0, 0],
                    [19, -19, 0, 0, 0, 0, 0, 0],
                ],
            ]
        ],
        dtype=np.float32,
    )

    produced = execution_im2col(
        x,
        idt,
        k_H,
        k_W,
        stride,
        ifm_ch,
        ifm_dim_H,
        ifm_dim_W,
        pad_amt,
        pad_val,
        dilation,
    )

    assert (produced == expected).all(), "Test failed for case number {}".format(
        case_id
    )

    case_id = 3
    idt = DataType.INT8
    k_H = 2
    k_W = 2
    stride = 2
    ifm_ch = 2
    ifm_dim_H = 5
    ifm_dim_W = 5
    pad_amt = [1, 1, 1, 1]
    pad_val = 0
    dilation = 2

    x = np.asarray(
        [
            [
                [[1, -1], [2, -2], [3, -3], [4, -4], [5, -5]],
                [[6, -6], [7, -7], [8, -8], [9, -9], [10, -10]],
                [[11, -11], [12, -12], [13, -13], [14, -14], [15, -15]],
                [[16, -16], [17, -17], [18, -18], [19, -19], [20, -20]],
                [[21, -21], [22, -22], [23, -23], [24, -24], [25, -25]],
            ]
        ],
        dtype=np.float32,
    )

    expected = np.asarray(
        [
            [
                [
                    [0, 0, 0, 0, 0, 0, 7, -7],
                    [0, 0, 0, 0, 7, -7, 9, -9],
                    [0, 0, 0, 0, 9, -9, 0, 0],
                ],
                [
                    [0, 0, 7, -7, 0, 0, 17, -17],
                    [7, -7, 9, -9, 17, -17, 19, -19],
                    [9, -9, 0, 0, 19, -19, 0, 0],
                ],
                [
                    [0, 0, 17, -17, 0, 0, 0, 0],
                    [17, -17, 19, -19, 0, 0, 0, 0],
                    [19, -19, 0, 0, 0, 0, 0, 0],
                ],
            ]
        ],
        dtype=np.float32,
    )

    produced = execution_im2col(
        x,
        idt,
        k_H,
        k_W,
        stride,
        ifm_ch,
        ifm_dim_H,
        ifm_dim_W,
        pad_amt,
        pad_val,
        dilation,
    )

    assert (produced == expected).all(), "Test failed for case number {}".format(
        case_id
    )

    case_id = 4
    idt = DataType.INT8
    k_H = 3
    k_W = 3
    stride = 2
    ifm_ch = 2
    ifm_dim_H = 5
    ifm_dim_W = 5
    pad_amt = [1, 1, 1, 1]
    pad_val = 0
    dilation = 2

    x = np.asarray(
        [
            [
                [[1, -1], [2, -2], [3, -3], [4, -4], [5, -5]],
                [[6, -6], [7, -7], [8, -8], [9, -9], [10, -10]],
                [[11, -11], [12, -12], [13, -13], [14, -14], [15, -15]],
                [[16, -16], [17, -17], [18, -18], [19, -19], [20, -20]],
                [[21, -21], [22, -22], [23, -23], [24, -24], [25, -25]],
            ]
        ],
        dtype=np.float32,
    )

    expected = np.asarray(
        [
            [
                [
                    [0, 0, 0, 0, 0, 0, 0, 0, 7, -7, 9, -9, 0, 0, 17, -17, 19, -19],
                    [0, 0, 0, 0, 0, 0, 7, -7, 9, -9, 0, 0, 17, -17, 19, -19, 0, 0],
                ],
                [
                    [0, 0, 7, -7, 9, -9, 0, 0, 17, -17, 19, -19, 0, 0, 0, 0, 0, 0],
                    [7, -7, 9, -9, 0, 0, 17, -17, 19, -19, 0, 0, 0, 0, 0, 0, 0, 0],
                ],
            ]
        ],
        dtype=np.float32,
    )

    produced = execution_im2col(
        x,
        idt,
        k_H,
        k_W,
        stride,
        ifm_ch,
        ifm_dim_H,
        ifm_dim_W,
        pad_amt,
        pad_val,
        dilation,
    )

    assert (produced == expected).all(), "Test failed for case number {}".format(
        case_id
    )

    case_id = 5
    idt = DataType.INT8
    k_H = 2
    k_W = 1
    stride = 1
    ifm_ch = 2
    ifm_dim_H = 5
    ifm_dim_W = 1
    pad_amt = [0, 0, 0, 0]
    pad_val = 0
    dilation = 1

    x = np.asarray(
        [[[[1, -1]], [[2, -2]], [[3, -3]], [[4, -4]], [[5, -5]]]],
        dtype=np.float32,
    )

    expected = np.asarray(
        [[[[1, -1, 2, -2]], [[2, -2, 3, -3]], [[3, -3, 4, -4]], [[4, -4, 5, -5]]]],
        dtype=np.float32,
    )

    produced = execution_im2col(
        x,
        idt,
        k_H,
        k_W,
        stride,
        ifm_ch,
        ifm_dim_H,
        ifm_dim_W,
        pad_amt,
        pad_val,
        dilation,
    )

    assert (produced == expected).all(), "Test failed for case number {}".format(
        case_id
    )

    case_id = 6
    idt = DataType.INT8
    k_H = 2
    k_W = 1
    stride = 1
    ifm_ch = 2
    ifm_dim_H = 5
    ifm_dim_W = 1
    pad_amt = [0, 0, 0, 0]
    pad_val = 0
    dilation = 2

    x = np.asarray(
        [[[[1, -1]], [[2, -2]], [[3, -3]], [[4, -4]], [[5, -5]]]],
        dtype=np.float32,
    )

    expected = np.asarray(
        [[[[1, -1, 3, -3]], [[2, -2, 4, -4]], [[3, -3, 5, -5]]]],
        dtype=np.float32,
    )

    produced = execution_im2col(
        x,
        idt,
        k_H,
        k_W,
        stride,
        ifm_ch,
        ifm_dim_H,
        ifm_dim_W,
        pad_amt,
        pad_val,
        dilation,
    )

    assert (produced == expected).all(), "Test failed for case number {}".format(
        case_id
    )

    case_id = 7
    idt = DataType.INT8
    k_H = 2
    k_W = 1
    stride = 1
    ifm_ch = 2
    ifm_dim_H = 5
    ifm_dim_W = 1
    pad_amt = [1, 0, 1, 0]
    pad_val = 0
    dilation = 2

    x = np.asarray(
        [[[[1, -1]], [[2, -2]], [[3, -3]], [[4, -4]], [[5, -5]]]],
        dtype=np.float32,
    )

    expected = np.asarray(
        [
            [
                [[0, 0, 2, -2]],
                [[1, -1, 3, -3]],
                [[2, -2, 4, -4]],
                [[3, -3, 5, -5]],
                [[4, -4, 0, 0]],
            ]
        ],
        dtype=np.float32,
    )

    produced = execution_im2col(
        x,
        idt,
        k_H,
        k_W,
        stride,
        ifm_ch,
        ifm_dim_H,
        ifm_dim_W,
        pad_amt,
        pad_val,
        dilation,
    )

    assert (produced == expected).all(), "Test failed for case number {}".format(
        case_id
    )

    case_id = 8
    idt = DataType.INT8
    k_H = 2
    k_W = 1
    stride = 2
    ifm_ch = 2
    ifm_dim_H = 5
    ifm_dim_W = 1
    pad_amt = [1, 0, 1, 0]
    pad_val = 0
    dilation = 2

    x = np.asarray(
        [[[[1, -1]], [[2, -2]], [[3, -3]], [[4, -4]], [[5, -5]]]],
        dtype=np.float32,
    )

    expected = np.asarray(
        [[[[0, 0, 2, -2]], [[2, -2, 4, -4]], [[4, -4, 0, 0]]]],
        dtype=np.float32,
    )

    produced = execution_im2col(
        x,
        idt,
        k_H,
        k_W,
        stride,
        ifm_ch,
        ifm_dim_H,
        ifm_dim_W,
        pad_amt,
        pad_val,
        dilation,
    )

    assert (produced == expected).all(), "Test failed for case number {}".format(
        case_id
    )

    case_id = 9
    idt = DataType.INT8
    k_H = 3
    k_W = 1
    stride = 2
    ifm_ch = 2
    ifm_dim_H = 5
    ifm_dim_W = 1
    pad_amt = [1, 0, 1, 0]
    pad_val = 0
    dilation = 2

    x = np.asarray(
        [[[[1, -1]], [[2, -2]], [[3, -3]], [[4, -4]], [[5, -5]]]],
        dtype=np.float32,
    )

    expected = np.asarray(
        [[[[0, 0, 2, -2, 4, -4]], [[2, -2, 4, -4, 0, 0]]]],
        dtype=np.float32,
    )

    produced = execution_im2col(
        x,
        idt,
        k_H,
        k_W,
        stride,
        ifm_ch,
        ifm_dim_H,
        ifm_dim_W,
        pad_amt,
        pad_val,
        dilation,
    )

    assert (produced == expected).all(), "Test failed for case number {}".format(
        case_id
    )


# Configurations tested:
# case id     | 0       | 1    | 2    | 3    | 4    | 5    | 6    | 7    | 8    |
# idt         | Bipolar | INT8 | INT8 | INT8 | INT8 | INT8 | INT8 | INT8 | INT8 |
# ifm_dim_H   | 4       | 4    | 4    | 4    | 4    | 4    | 5    | 5    | 5    |
# ifm_dim_W   | 4       | 4    | 4    | 5    | 5    | 5    | 1    | 1    | 1    |
# ifm_ch      | 1       | 2    | 2    | 2    | 2    | 2    | 2    | 2    | 2    |
# pad_amt     | 0       | 0    | 1    | 0    | 0    | 1    | 0    | 1    | 1    |
# pad_val     | 0       | 0    | 0    | 0    | 0    | 0    | 0    | 0    | 0    |
# k_H         | 2       | 2    | 2    | 2    | 3    | 3    | 3    | 3    | 3    |
# k_W         | 2       | 2    | 2    | 2    | 2    | 2    | 1    | 1    | 1    |
# stride      | 1       | 1    | 1    | 1    | 1    | 1    | 1    | 1    | 2    |
# dilations   | 1       | 1    | 1    | 1    | 1    | 1    | 1    | 1    | 1    |
def test_im2col():
    case_id = 0
    # bipolar inputs with following im2col parameters
    idt = DataType.BIPOLAR
    k_h = 2
    k_w = 2
    stride = 1
    ifm_ch = 1
    ifm_dim_h = 4
    ifm_dim_w = 4
    pad_amt = [0, 0, 0, 0]
    pad_amt_h = pad_amt[0] + pad_amt[2]
    pad_amt_w = pad_amt[1] + pad_amt[3]
    pad_val = 0

    ofm_dim_h = compute_conv_output_dim(ifm_dim_h, k_h, stride, pad_amt_h)
    ofm_dim_w = compute_conv_output_dim(ifm_dim_w, k_w, stride, pad_amt_w)

    x = np.asarray(
        [
            -1.0,
            -1.0,
            1.0,
            1.0,
            1.0,
            -1.0,
            1.0,
            -1.0,
            -1.0,
            1.0,
            -1.0,
            -1.0,
            1.0,
            1.0,
            1.0,
            1.0,
        ],
        dtype=np.float32,
    ).reshape(1, ifm_dim_h, ifm_dim_w, ifm_ch)

    expected = np.asarray(
        [
            -1.0,
            -1.0,
            1.0,
            -1.0,
            -1.0,
            1.0,
            -1.0,
            1.0,
            1.0,
            1.0,
            1.0,
            -1.0,
            1.0,
            -1.0,
            -1.0,
            1.0,
            -1.0,
            1.0,
            1.0,
            -1.0,
            1.0,
            -1.0,
            -1.0,
            -1.0,
            -1.0,
            1.0,
            1.0,
            1.0,
            1.0,
            -1.0,
            1.0,
            1.0,
            -1.0,
            -1.0,
            1.0,
            1.0,
        ],
        dtype=np.float32,
    ).reshape(1, ofm_dim_h, ofm_dim_w, k_h * k_w * ifm_ch)

    produced = execution_im2col(
        x, idt, k_h, k_w, stride, ifm_ch, ifm_dim_h, ifm_dim_w, pad_amt, pad_val
    )
    assert (produced == expected).all(), "Test failed for case number {}".format(
        case_id
    )

    case_id = 1
    idt = DataType.INT8
    k_h = 2
    k_w = 2
    stride = 1
    ifm_ch = 2
    ifm_dim_h = 4
    ifm_dim_w = 4
    pad_amt = [0, 0, 0, 0]
    pad_val = 0

    x = np.asarray(
        [
            [
                [[1, -1], [2, -2], [3, -3], [4, -4]],
                [[5, -5], [6, -6], [7, -7], [8, -8]],
                [[9, -9], [10, -10], [11, -11], [12, -12]],
                [[13, -13], [14, -14], [15, -15], [16, -16]],
            ]
        ],
        dtype=np.float32,
    )

    expected = np.asarray(
        [
            [
                [
                    [1.0, -1.0, 2.0, -2.0, 5.0, -5.0, 6.0, -6.0],
                    [2.0, -2.0, 3.0, -3.0, 6.0, -6.0, 7.0, -7.0],
                    [3.0, -3.0, 4.0, -4.0, 7.0, -7.0, 8.0, -8.0],
                ],
                [
                    [5.0, -5.0, 6.0, -6.0, 9.0, -9.0, 10.0, -10.0],
                    [6.0, -6.0, 7.0, -7.0, 10.0, -10.0, 11.0, -11.0],
                    [7.0, -7.0, 8.0, -8.0, 11.0, -11.0, 12.0, -12.0],
                ],
                [
                    [9.0, -9.0, 10.0, -10.0, 13.0, -13.0, 14.0, -14.0],
                    [10.0, -10.0, 11.0, -11.0, 14.0, -14.0, 15.0, -15.0],
                    [11.0, -11.0, 12.0, -12.0, 15.0, -15.0, 16.0, -16.0],
                ],
            ]
        ],
        dtype=np.float32,
    )

    produced = execution_im2col(
        x, idt, k_h, k_w, stride, ifm_ch, ifm_dim_h, ifm_dim_w, pad_amt, pad_val
    )
    assert (produced == expected).all(), "Test failed for case number {}".format(
        case_id
    )

    case_id = 2
    idt = DataType.INT8
    k_h = 2
    k_w = 2
    stride = 1
    ifm_ch = 2
    ifm_dim_h = 4
    ifm_dim_w = 4
    pad_amt = [1, 1, 1, 1]
    pad_val = 0

    x = np.asarray(
        [
            [
                [[1, -1], [2, -2], [3, -3], [4, -4]],
                [[5, -5], [6, -6], [7, -7], [8, -8]],
                [[9, -9], [10, -10], [11, -11], [12, -12]],
                [[13, -13], [14, -14], [15, -15], [16, -16]],
            ]
        ],
        dtype=np.float32,
    )

    expected = np.asarray(
        [
            [
                [
                    [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0, -1.0],
                    [0.0, 0.0, 0.0, 0.0, 1.0, -1.0, 2.0, -2.0],
                    [0.0, 0.0, 0.0, 0.0, 2.0, -2.0, 3.0, -3.0],
                    [0.0, 0.0, 0.0, 0.0, 3.0, -3.0, 4.0, -4.0],
                    [0.0, 0.0, 0.0, 0.0, 4.0, -4.0, 0.0, 0.0],
                ],
                [
                    [0.0, 0.0, 1.0, -1.0, 0.0, 0.0, 5.0, -5.0],
                    [1.0, -1.0, 2.0, -2.0, 5.0, -5.0, 6.0, -6.0],
                    [2.0, -2.0, 3.0, -3.0, 6.0, -6.0, 7.0, -7.0],
                    [3.0, -3.0, 4.0, -4.0, 7.0, -7.0, 8.0, -8.0],
                    [4.0, -4.0, 0.0, 0.0, 8.0, -8.0, 0.0, 0.0],
                ],
                [
                    [0.0, 0.0, 5.0, -5.0, 0.0, 0.0, 9.0, -9.0],
                    [5.0, -5.0, 6.0, -6.0, 9.0, -9.0, 10.0, -10.0],
                    [6.0, -6.0, 7.0, -7.0, 10.0, -10.0, 11.0, -11.0],
                    [7.0, -7.0, 8.0, -8.0, 11.0, -11.0, 12.0, -12.0],
                    [8.0, -8.0, 0.0, 0.0, 12.0, -12.0, 0.0, 0.0],
                ],
                [
                    [0.0, 0.0, 9.0, -9.0, 0.0, 0.0, 13.0, -13.0],
                    [9.0, -9.0, 10.0, -10.0, 13.0, -13.0, 14.0, -14.0],
                    [10.0, -10.0, 11.0, -11.0, 14.0, -14.0, 15.0, -15.0],
                    [11.0, -11.0, 12.0, -12.0, 15.0, -15.0, 16.0, -16.0],
                    [12.0, -12.0, 0.0, 0.0, 16.0, -16.0, 0.0, 0.0],
                ],
                [
                    [0.0, 0.0, 13.0, -13.0, 0.0, 0.0, 0.0, 0.0],
                    [13.0, -13.0, 14.0, -14.0, 0.0, 0.0, 0.0, 0.0],
                    [14.0, -14.0, 15.0, -15.0, 0.0, 0.0, 0.0, 0.0],
                    [15.0, -15.0, 16.0, -16.0, 0.0, 0.0, 0.0, 0.0],
                    [16.0, -16.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
                ],
            ]
        ],
        dtype=np.float32,
    )

    produced = execution_im2col(
        x, idt, k_h, k_w, stride, ifm_ch, ifm_dim_h, ifm_dim_w, pad_amt, pad_val
    )
    assert (produced == expected).all(), "Test failed for case number {}".format(
        case_id
    )

    case_id = 3
    idt = DataType.INT8
    k_h = 2
    k_w = 2
    stride = 1
    ifm_ch = 2
    ifm_dim_h = 4
    ifm_dim_w = 5
    pad_amt = [0, 0, 0, 0]
    pad_val = 0

    x = np.asarray(
        [
            [
                [[1, -1], [2, -2], [3, -3], [4, -4], [5, -5]],
                [[6, -6], [7, -7], [8, -8], [9, -9], [10, -10]],
                [[11, -11], [12, -12], [13, -13], [14, -14], [15, -15]],
                [[16, -16], [17, -17], [18, -18], [19, -19], [20, -20]],
            ]
        ],
        dtype=np.float32,
    )

    expected = np.asarray(
        [
            [
                [
                    [1, -1, 2, -2, 6, -6, 7, -7],
                    [2, -2, 3, -3, 7, -7, 8, -8],
                    [3, -3, 4, -4, 8, -8, 9, -9],
                    [4, -4, 5, -5, 9, -9, 10, -10],
                ],
                [
                    [6, -6, 7, -7, 11, -11, 12, -12],
                    [7, -7, 8, -8, 12, -12, 13, -13],
                    [8, -8, 9, -9, 13, -13, 14, -14],
                    [9, -9, 10, -10, 14, -14, 15, -15],
                ],
                [
                    [11, -11, 12, -12, 16, -16, 17, -17],
                    [12, -12, 13, -13, 17, -17, 18, -18],
                    [13, -13, 14, -14, 18, -18, 19, -19],
                    [14, -14, 15, -15, 19, -19, 20, -20],
                ],
            ]
        ],
        dtype=np.float32,
    )

    produced = execution_im2col(
        x, idt, k_h, k_w, stride, ifm_ch, ifm_dim_h, ifm_dim_w, pad_amt, pad_val
    )
    assert (produced == expected).all(), "Test failed for case number {}".format(
        case_id
    )

    case_id = 4
    idt = DataType.INT8
    k_h = 3
    k_w = 2
    stride = 1
    ifm_ch = 2
    ifm_dim_h = 4
    ifm_dim_w = 5
    pad_amt = [0, 0, 0, 0]
    pad_val = 0

    x = np.asarray(
        [
            [
                [[1, -1], [2, -2], [3, -3], [4, -4], [5, -5]],
                [[6, -6], [7, -7], [8, -8], [9, -9], [10, -10]],
                [[11, -11], [12, -12], [13, -13], [14, -14], [15, -15]],
                [[16, -16], [17, -17], [18, -18], [19, -19], [20, -20]],
            ]
        ],
        dtype=np.float32,
    )

    expected = np.asarray(
        [
            [
                [
                    [1, -1, 2, -2, 6, -6, 7, -7, 11, -11, 12, -12],
                    [2, -2, 3, -3, 7, -7, 8, -8, 12, -12, 13, -13],
                    [3, -3, 4, -4, 8, -8, 9, -9, 13, -13, 14, -14],
                    [4, -4, 5, -5, 9, -9, 10, -10, 14, -14, 15, -15],
                ],
                [
                    [6, -6, 7, -7, 11, -11, 12, -12, 16, -16, 17, -17],
                    [7, -7, 8, -8, 12, -12, 13, -13, 17, -17, 18, -18],
                    [8, -8, 9, -9, 13, -13, 14, -14, 18, -18, 19, -19],
                    [9, -9, 10, -10, 14, -14, 15, -15, 19, -19, 20, -20],
                ],
            ]
        ],
        dtype=np.float32,
    )

    produced = execution_im2col(
        x, idt, k_h, k_w, stride, ifm_ch, ifm_dim_h, ifm_dim_w, pad_amt, pad_val
    )
    assert (produced == expected).all(), "Test failed for case number {}".format(
        case_id
    )

    case_id = 5
    idt = DataType.INT8
    k_h = 3
    k_w = 2
    stride = 1
    ifm_ch = 2
    ifm_dim_h = 4
    ifm_dim_w = 5
    pad_amt = [1, 1, 1, 1]
    pad_val = 0

    x = np.asarray(
        [
            [
                [[1, -1], [2, -2], [3, -3], [4, -4], [5, -5]],
                [[6, -6], [7, -7], [8, -8], [9, -9], [10, -10]],
                [[11, -11], [12, -12], [13, -13], [14, -14], [15, -15]],
                [[16, -16], [17, -17], [18, -18], [19, -19], [20, -20]],
            ]
        ],
        dtype=np.float32,
    )

    expected = np.asarray(
        [
            [
                [
                    [0, 0, 0, 0, 0, 0, 1, -1, 0, 0, 6, -6],
                    [0, 0, 0, 0, 1, -1, 2, -2, 6, -6, 7, -7],
                    [0, 0, 0, 0, 2, -2, 3, -3, 7, -7, 8, -8],
                    [0, 0, 0, 0, 3, -3, 4, -4, 8, -8, 9, -9],
                    [0, 0, 0, 0, 4, -4, 5, -5, 9, -9, 10, -10],
                    [0, 0, 0, 0, 5, -5, 0, 0, 10, -10, 0, 0],
                ],
                [
                    [0, 0, 1, -1, 0, 0, 6, -6, 0, 0, 11, -11],
                    [1, -1, 2, -2, 6, -6, 7, -7, 11, -11, 12, -12],
                    [2, -2, 3, -3, 7, -7, 8, -8, 12, -12, 13, -13],
                    [3, -3, 4, -4, 8, -8, 9, -9, 13, -13, 14, -14],
                    [4, -4, 5, -5, 9, -9, 10, -10, 14, -14, 15, -15],
                    [5, -5, 0, 0, 10, -10, 0, 0, 15, -15, 0, 0],
                ],
                [
                    [0, 0, 6, -6, 0, 0, 11, -11, 0, 0, 16, -16],
                    [6, -6, 7, -7, 11, -11, 12, -12, 16, -16, 17, -17],
                    [7, -7, 8, -8, 12, -12, 13, -13, 17, -17, 18, -18],
                    [8, -8, 9, -9, 13, -13, 14, -14, 18, -18, 19, -19],
                    [9, -9, 10, -10, 14, -14, 15, -15, 19, -19, 20, -20],
                    [10, -10, 0, 0, 15, -15, 0, 0, 20, -20, 0, 0],
                ],
                [
                    [0, 0, 11, -11, 0, 0, 16, -16, 0, 0, 0, 0],
                    [11, -11, 12, -12, 16, -16, 17, -17, 0, 0, 0, 0],
                    [12, -12, 13, -13, 17, -17, 18, -18, 0, 0, 0, 0],
                    [13, -13, 14, -14, 18, -18, 19, -19, 0, 0, 0, 0],
                    [14, -14, 15, -15, 19, -19, 20, -20, 0, 0, 0, 0],
                    [15, -15, 0, 0, 20, -20, 0, 0, 0, 0, 0, 0],
                ],
            ]
        ],
        dtype=np.float32,
    )

    produced = execution_im2col(
        x, idt, k_h, k_w, stride, ifm_ch, ifm_dim_h, ifm_dim_w, pad_amt, pad_val
    )
    assert (produced == expected).all(), "Test failed for case number {}".format(
        case_id
    )

    case_id = 6
    idt = DataType.INT8
    k_h = 3
    k_w = 1
    stride = 1
    ifm_ch = 2
    ifm_dim_h = 5
    ifm_dim_w = 1
    pad_amt = [0, 0, 0, 0]
    pad_val = 0

    x = np.asarray(
        [[[[1, -1]], [[2, -2]], [[3, -3]], [[4, -4]], [[5, -5]]]],
        dtype=np.float32,
    )

    expected = np.asarray(
        [[[[1, -1, 2, -2, 3, -3]], [[2, -2, 3, -3, 4, -4]], [[3, -3, 4, -4, 5, -5]]]],
        dtype=np.float32,
    )

    produced = execution_im2col(
        x, idt, k_h, k_w, stride, ifm_ch, ifm_dim_h, ifm_dim_w, pad_amt, pad_val
    )
    assert (produced == expected).all(), "Test failed for case number {}".format(
        case_id
    )

    case_id = 7
    idt = DataType.INT8
    k_h = 3
    k_w = 1
    stride = 1
    ifm_ch = 2
    ifm_dim_h = 5
    ifm_dim_w = 1
    pad_amt = [1, 0, 1, 0]
    pad_val = 0

    x = np.asarray(
        [[[[1, -1]], [[2, -2]], [[3, -3]], [[4, -4]], [[5, -5]]]],
        dtype=np.float32,
    )

    expected = np.asarray(
        [
            [
                [[0, 0, 1, -1, 2, -2]],
                [[1, -1, 2, -2, 3, -3]],
                [[2, -2, 3, -3, 4, -4]],
                [[3, -3, 4, -4, 5, -5]],
                [[4, -4, 5, -5, 0, 0]],
            ]
        ],
        dtype=np.float32,
    )

    produced = execution_im2col(
        x, idt, k_h, k_w, stride, ifm_ch, ifm_dim_h, ifm_dim_w, pad_amt, pad_val
    )
    assert (produced == expected).all(), "Test failed for case number {}".format(
        case_id
    )

    case_id = 8
    idt = DataType.INT8
    k_h = 3
    k_w = 1
    stride = 2
    ifm_ch = 2
    ifm_dim_h = 5
    ifm_dim_w = 1
    pad_amt = [1, 0, 1, 0]
    pad_val = 0

    x = np.asarray(
        [[[[1, -1]], [[2, -2]], [[3, -3]], [[4, -4]], [[5, -5]]]],
        dtype=np.float32,
    )

    expected = np.asarray(
        [[[[0, 0, 1, -1, 2, -2]], [[2, -2, 3, -3, 4, -4]], [[4, -4, 5, -5, 0, 0]]]],
        dtype=np.float32,
    )

    produced = execution_im2col(
        x, idt, k_h, k_w, stride, ifm_ch, ifm_dim_h, ifm_dim_w, pad_amt, pad_val
    )
    assert (produced == expected).all(), "Test failed for case number {}".format(
        case_id
    )


def test_im2col_infer_shapes():
    idt = DataType.BIPOLAR
    k_h = 2
    k_w = 2
    stride = 1
    ifm_ch = 1
    ifm_dim_h = 4
    ifm_dim_w = 4
    pad_amt = [0, 0, 0, 0]  # default
    pad_amt_h = pad_amt[0] + pad_amt[2]
    pad_amt_w = pad_amt[1] + pad_amt[3]
    dilation = 1

    ofm_dim_h = compute_conv_output_dim(ifm_dim_h, k_h, stride, pad_amt_h, dilation)
    ofm_dim_w = compute_conv_output_dim(ifm_dim_w, k_w, stride, pad_amt_w, dilation)

    # set up onnx model
    inp = helper.make_tensor_value_info(
        "inp", TensorProto.FLOAT, [1, ifm_dim_h, ifm_dim_w, ifm_ch]
    )
    outp = helper.make_tensor_value_info(
        "outp", TensorProto.FLOAT, [1, ofm_dim_h, ofm_dim_w, k_h * k_w * ifm_ch]
    )

    abs_node = helper.make_node("Abs", inputs=["inp"], outputs=["abs"])

    Im2Col_node = helper.make_node(
        "Im2Col",
        ["abs"],
        ["im2col"],
        domain="finn.custom_op.general",
        stride=stride,
        kernel_size=[k_h, k_w],
        input_shape="(1,{},{},{})".format(ifm_dim_h, ifm_dim_w, ifm_ch),
        dilations=dilation,
    )

    abs1_node = helper.make_node("Abs", inputs=["im2col"], outputs=["outp"])

    graph = helper.make_graph(
        nodes=[abs_node, Im2Col_node, abs1_node],
        name="shape_graph",
        inputs=[inp],
        outputs=[outp],
        value_info=[
            helper.make_tensor_value_info(
                "abs", TensorProto.FLOAT, [1, ifm_dim_h, ifm_dim_w, ifm_ch]
            ),
            helper.make_tensor_value_info(
                "im2col",
                TensorProto.FLOAT,
                [1, ofm_dim_h, ofm_dim_w, k_h * k_w * ifm_ch],
            ),
        ],
    )

    model = helper.make_model(graph, producer_name="shape-model")
    model = ModelWrapper(model)

    model.set_tensor_datatype("inp", idt)

    # test shape inference
    model.transform(InferShapes())
    assert model.get_tensor_shape("im2col") == [
        1,
        ofm_dim_h,
        ofm_dim_w,
        k_h * k_w * ifm_ch,
    ]
