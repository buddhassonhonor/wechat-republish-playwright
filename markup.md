<textarea data-v-11cbc270="" id="js_description" placeholder="选填，不填写则默认抓取正文开头部分文字，摘要会在转发卡片和公众号会话展示。" name="digest" max-length="120" class="frm_textarea js_desc js_counter js_field"></textarea>


<div contenteditable="true" translate="no" class="ProseMirror" style="padding: 0px 4px; min-height: 536px;"><div class="editor_content_placeholder edui-default ProseMirror-widget" contenteditable="false" style="position: absolute; pointer-events: none; user-select: none; font-size: 14px; z-index: -1; left: 4px;">从这里开始写正文</div><section><span leaf=""><br class="ProseMirror-trailingBreak"></span></section></div>


<div id="js_cover_area" class="setting-group__cover setting-group__cover_primary">
                        <div class="select-cover__btn js_cover_btn_area select-cover__mask">
                          <i class="icon20_common add_cover" style="display: inline-block;"></i>
                          <span class="btn-text js_share_type_none_image" style="display: block;">拖拽或选择封面</span>
                          <span class="btn-text js_share_type_image" style="display: none">默认首图为封面</span>
                        </div>
                        <!-- 封面图加载出来之前的 loading 状态 -->
                        <div class="select-cover__loading__mask js_cover_loading">
                          <i class="select-cover__loading weui-desktop-loading"></i>
                        </div>
                        <!-- 默认隐藏，选中图片后才显示 -->
                        <!-- <div class="select-cover__preview js_cover_preview_new" style="display: none;">
                            <div class="select-cover__icon__modify js_cover_btn_area">
                                <a href="javascript:;" class="icon18_common del_gray js_modifyCover" onclick="return false;">修改</a>
                            </div>
                            <input type="hidden" class="js_field js_file_id" name="file_id">
                            <input type="hidden" class="js_field js_cdn_url" name="cdn_url">
                            <input type="hidden" class="js_field js_cdn_url_back" name="cdn_url_back">
                            <input type="hidden" class="js_show_cover_pic js_field" data-type='checkbox' name="show_cover_pic">
                        </div> -->

                        <div class="js_cover_preview_new select-cover__preview first_appmsg_cover" style="display: none; background-image: url(&quot;&quot;);">

                          <div class="js_splice-cover-con select-splice-cover">
                            <div class="js_splice-cover splice-cover-preview"></div>
                            <div class="js_splice-cover splice-cover-preview"></div>
                            <div class="js_splice-cover splice-cover-preview"></div>
                          </div>

                          <div class="weui-desktop-link-group cover-hover-link-group">
                            <div class="weui-desktop-popover__wrp weui-desktop-link">
                              <span class="weui-desktop-popover__target">
                                <div class="weui-desktop-tooltip__wrp">
                                  <a href="javascript:;" class="weui-desktop-icon20 weui-desktop-icon-btn  icon20_common comm_edit js_modifyCover" onclick="return false;">
                                  </a>
                                  <span class="weui-desktop-tooltip weui-desktop-tooltip__down-center" style="display: none;">修改</span>
                                </div>
                              </span>
                            </div>

                            <div class="js_chooseCoverWrap weui-desktop-popover__wrp weui-desktop-link cover-hover-link-choose" style="display: flex;">
                              <span class="weui-desktop-popover__target">
                                <div class="weui-desktop-tooltip__wrp">
                                  <a href="javascript:;" class="weui-desktop-icon20 weui-desktop-icon-btn icon20_common comm_replace js_chooseCover" onclick="return false;">
                                  </a>
                                  <span class="weui-desktop-tooltip weui-desktop-tooltip__down-center" style="display: none;">换一张</span>
                                </div>
                              </span>
                              <!-- hover 上去显示的工具条 -->
                              <div class="pop-opr__group js_cover_opr js_cover_btn_area">
                                <ul class="pop-opr__list">
                                  <li class="pop-opr__item">
                                    <a href="javascript:;" class="pop-opr__button js_selectCoverFromContent" onclick="return false;">从正文选择</a>
                                  </li>
                                  <li class="pop-opr__item">
                                    <a href="javascript:;" class="pop-opr__button js_imagedialog" onclick="return false;">从图片库选择</a>
                                  </li>
                                  
                                  <li class="pop-opr__item">
                                    <a href="javascript:;" class="pop-opr__button js_imageScan" onclick="return false;">微信扫码上传</a>
                                  </li>
                                  
                                  
                                  <li class="pop-opr__item">
                                    <a href="javascript:;" class="pop-opr__button js_aiImage" onclick="return false;">AI 配图</a>
                                  </li>
                                  
                                </ul>
                              </div>
                            </div>
                          </div>

                          <!-- <input type="hidden" class="js_field js_file_id" name="file_id">
                          <input type="hidden" class="js_field js_cdn_url" name="cdn_url">
                          <input type="hidden" class="js_field js_cdn_url_back" name="cdn_url_back">
                          <input type="hidden" class="js_show_cover_pic js_field" data-type='checkbox' name="show_cover_pic"> -->
                        </div>

                        <!-- 封面图加载出来之前的 loading 状态 -->
                        <div class="select-cover__loading__mask preview-square js_cover_loading js_cover_loading_square" style="display: none;">
                          <i class="select-cover__loading weui-desktop-loading"></i>
                        </div>

                        <div class="js_cover_preview_square select-cover__preview preview-square" style="display: none;">
                          <div class="weui-desktop-link-group cover-hover-link-group">
                            <div class="weui-desktop-popover__wrp weui-desktop-link">
                              <span class="weui-desktop-popover__target">
                                <div class="weui-desktop-tooltip__wrp">
                                  <a href="javascript:;" class="weui-desktop-icon20 weui-desktop-icon-btn  icon20_common comm_edit js_modifyCover" onclick="return false;">
                                  </a>
                                  <span class="weui-desktop-tooltip weui-desktop-tooltip__down-center" style="display: none;">修改</span>
                                </div>
                              </span>
                            </div>

                            <div class="js_chooseCoverWrap weui-desktop-popover__wrp weui-desktop-link cover-hover-link-choose" style="display: flex;">
                              <span class="weui-desktop-popover__target">
                                <div class="weui-desktop-tooltip__wrp">
                                  <a href="javascript:;" class="weui-desktop-icon20 weui-desktop-icon-btn icon20_common comm_replace js_chooseCover" onclick="return false;">
                                  </a>
                                  <span class="weui-desktop-tooltip weui-desktop-tooltip__down-center" style="display: none;">换一张</span>
                                </div>
                              </span>
                              <!-- hover 上去显示的工具条 -->
                              <div class="pop-opr__group js_cover_opr js_cover_btn_area">
                                <ul class="pop-opr__list">
                                    <li class="pop-opr__item">
                                        <a href="javascript:;" class="pop-opr__button js_selectCoverFromContent" onclick="return false;">从正文选择</a>
                                    </li>
                                    <li class="pop-opr__item">
                                        <a href="javascript:;" class="pop-opr__button js_imagedialog" onclick="return false;">从图片库选择</a>
                                    </li>
                                    
                                    <li class="pop-opr__item">
                                      <a href="javascript:;" class="pop-opr__button js_imageScan" onclick="return false;">微信扫码上传</a>
                                    </li>
                                    
                                    
                                    <li class="pop-opr__item">
                                      <a href="javascript:;" class="pop-opr__button js_aiImage" onclick="return false;">AI 配图</a>
                                    </li>
                                    
                                </ul>
                              </div>
                            </div>
                          </div>
                        </div>


                        <div class="cover_drop_inner_wrp setting_group__cover_primary">
                          <!-- 拖拽外层引导样式 -->
                          <div class="select-cover_outer_drop">
                            <i class="icon20_common drop_cover"></i>
                            <span class="btn-text">拖拽图片至此区域</span>
                          </div>
                          <!-- 拖拽内层引导样式 -->
                          <div class="select-cover_inner_drop">
                            <span class="btn-text" id="inner_drop">松开鼠标
                            <span class="btn-text" id="inner_drop">添加图片</span>
                          </span></div>
                          <!-- 拖拽多张引导样式 -->
                          <div class="select-cover_multi_drop">
                            <i class="icon20_common drop_forbid"></i>
                            <span class="btn-text">最多添加1张图片</span>
                          </div>
                        </div>

                        <div class="pop-opr__group pop-opr__group-select-cover js_cover_null_pop js_cover_opr" id="js_cover_null" style="display: block;">
                          <ul class="pop-opr__list">
                            <li class="pop-opr__item">
                              <a href="javascript:;" class="pop-opr__button js_selectCoverFromContent" onclick="return false;">从正文选择<br><span class="js_selectVideoCoverTips" style="color:#7E8081;display:none">可选视频封面</span></a>
                            </li>
                            <li class="pop-opr__item">
                              <a href="javascript:;" class="pop-opr__button js_imagedialog" onclick="return false;">从图片库选择</a>
                            </li>
                            
                            <li class="pop-opr__item">
                              <a href="javascript:;" class="pop-opr__button js_imageScan" onclick="return false;">微信扫码上传</a>
                            </li>
                            
                            
                            <li class="pop-opr__item">
                              <a href="javascript:;" class="pop-opr__button js_aiImage" onclick="return false;">AI 配图</a>
                            </li>
                            
                          </ul>
                        </div>
                    </div>