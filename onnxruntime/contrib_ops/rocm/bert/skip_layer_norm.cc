// Copyright (c) Microsoft Corporation. All rights reserved.
// Licensed under the MIT License.

#include "contrib_ops/rocm/bert/skip_layer_norm.h"

#include "core/providers/rocm/rocm_common.h"
#include "contrib_ops/cpu/skip_layer_norm_helper.h"
#include "contrib_ops/rocm/bert/skip_layer_norm_impl.h"
#include "contrib_ops/rocm/bert/transformer_common.h"

namespace onnxruntime {
namespace contrib {
namespace rocm {

#define REGISTER_KERNEL_TYPED(T)                                  \
  ONNX_OPERATOR_TYPED_KERNEL_EX(                                  \
      SkipLayerNormalization,                                     \
      kMSDomain,                                                  \
      1,                                                          \
      T,                                                          \
      kRocmExecutionProvider,                                     \
      (*KernelDefBuilder::Create())                               \
          .TypeConstraint("T", DataTypeImpl::GetTensorType<T>()), \
      SkipLayerNorm<T, false>);                                   \
  ONNX_OPERATOR_TYPED_KERNEL_EX(                                  \
      SkipSimplifiedLayerNormalization,                           \
      kMSDomain,                                                  \
      1,                                                          \
      T,                                                          \
      kRocmExecutionProvider,                                     \
      (*KernelDefBuilder::Create())                               \
          .TypeConstraint("T", DataTypeImpl::GetTensorType<T>()), \
      SkipLayerNorm<T, true>);

REGISTER_KERNEL_TYPED(float)
REGISTER_KERNEL_TYPED(MLFloat16)

using namespace ONNX_NAMESPACE;

template <typename T, bool Simplified>
SkipLayerNorm<T, Simplified>::SkipLayerNorm(const OpKernelInfo& op_kernel_info) : RocmKernel(op_kernel_info) {
  ORT_ENFORCE(op_kernel_info.GetAttr<float>("epsilon", &epsilon_).IsOK());
  ORT_ENFORCE(epsilon_ >= 0);
}

template <typename T, bool Simplified>
Status SkipLayerNorm<T, Simplified>::ComputeInternal(OpKernelContext* ctx) const {
  const Tensor* input = ctx->Input<Tensor>(0);
  const Tensor* skip = ctx->Input<Tensor>(1);
  const Tensor* gamma = ctx->Input<Tensor>(2);

  const Tensor* beta = Simplified ? nullptr : ctx->Input<Tensor>(3);
  const Tensor* bias = Simplified ? ctx->Input<Tensor>(3) : ctx->Input<Tensor>(4);

  Tensor* output = ctx->Output(0, input->Shape());

  // For inferencing, we support one more optional output which is the sum
  // of the input and skip tensors
  Tensor* skip_input_bias_add_output = ctx->Output(3, input->Shape());

  if (input->Shape().Size() == 0) {
    return Status::OK();
  }

  const auto& input_dims = input->Shape().GetDims();
  size_t input_dims_size = input_dims.size();
  const auto& skip_dims = skip->Shape().GetDims();
  size_t skip_dims_size = skip_dims.size();

  int hidden_size = static_cast<int>(input_dims[input_dims_size - 1]);

  ORT_RETURN_IF_ERROR(onnxruntime::contrib::skip_layer_norm_helper::CheckInputs<Tensor>(input,
                                                                                        skip,
                                                                                        gamma,
                                                                                        beta,
                                                                                        bias,
                                                                                        hidden_size,
                                                                                        input_dims_size));

  const bool skip_broadcasted = (skip_dims[0] == 1 || skip_dims_size == 2) ? true : false;
  const int skip_size = static_cast<int>(skip_dims[skip_dims_size - 1] * skip_dims[skip_dims_size - 2]);

  int64_t element_count = input->Shape().Size();
  typedef typename ToHipType<T>::MappedType HipT;

  return LaunchSkipLayerNormKernel<HipT, float, HipT, Simplified>(
      GetTuningContext(),
      ctx->GetComputeStream(),
      reinterpret_cast<HipT*>(output->MutableData<T>()),
      skip_input_bias_add_output != nullptr ? reinterpret_cast<HipT*>(skip_input_bias_add_output->MutableData<T>()) : nullptr,
      reinterpret_cast<const HipT*>(input->Data<T>()),
      reinterpret_cast<const HipT*>(skip->Data<T>()),
      reinterpret_cast<const HipT*>(gamma->Data<T>()),
      (beta != nullptr) ? reinterpret_cast<const HipT*>(beta->Data<T>()) : nullptr,
      (bias != nullptr) ? reinterpret_cast<const HipT*>(bias->Data<T>()) : nullptr,
      epsilon_,
      hidden_size,
      static_cast<int>(element_count),
      skip_broadcasted,
      skip_size);
}

}  // namespace rocm
}  // namespace contrib
}  // namespace onnxruntime
