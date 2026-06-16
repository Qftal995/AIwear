package com.bitejiuyeke.service;

import com.bitejiuyeke.dto.request.EditImageRequest;
import com.bitejiuyeke.dto.request.MergeImageRequest;
import com.bitejiuyeke.dto.request.SearchImageRequest;
import com.bitejiuyeke.dto.response.EditImageResponse;
import com.bitejiuyeke.dto.response.MergeImageResponse;
import com.bitejiuyeke.dto.response.SearchImageResponse;
import com.bitejiuyeke.dto.response.UploadImageResponse;
import com.bitejiuyeke.entity.ImageFile;
import org.springframework.web.multipart.MultipartFile;

import java.util.List;

// 文件服务接口
public interface FileService {

    // 上传图片：先保存到系统，再同步到OSS，并落库files表
    UploadImageResponse uploadImage(MultipartFile file, String authorization);

    // 查询当前用户上传的图片列表
    List<ImageFile> myImages(String authorization);

    // 搜索当前用户上传的图片
    List<SearchImageResponse> search(String authorization, SearchImageRequest searchImageRequest);

    // 编辑用户上传的图片
    EditImageResponse edit(String authorization, EditImageRequest editImageRequest);

    // 合并用户上传的图片
    MergeImageResponse merge(String authorization, MergeImageRequest mergeImageRequest);
}

