#include "4DPluginAPI.h"
#include "PrivateTypes.h"
#include "EntryPoints.h"
#include "ARRAY_TEXT.h"
#include "support/4DPlugin-JSON.h"
#include <cstdlib>
#include <cstring>
#include <map>
#include <set>

namespace {
bool allocatedEmpty;
bool named;
bool dying;
int callbackKind;
int callbackCount;
bool abortCallback;
std::map<PA_Unichar*, size_t> strings;
std::map<PA_Handle, size_t> handles;
std::set<PA_Picture> pictures;
const CUTF16String sample = { 'A', 0x65e5, 0xd83d, 0xde80 };
const CUTF8String sample8 = CUTF8String(
    reinterpret_cast<const uint8_t*>("A\xe6\x97\xa5\xf0\x9f\x9a\x80"));

void require(bool condition, const char* message) {
    if (!condition) {
        fprintf(stderr, "ownership assertion: %s\n", message);
        std::exit(1);
    }
}

PA_Unistring makeString(const PA_Unichar* data) {
    PA_Unistring result = {};
    while (data[result.fLength]) ++result.fLength;
    if (result.fLength || allocatedEmpty) {
        size_t bytes = (result.fLength + 1) * sizeof(PA_Unichar);
        result.fString = static_cast<PA_Unichar*>(std::malloc(bytes));
        std::memcpy(result.fString, data, bytes);
        PA_Unichar* pointer = result.fString;
        strings[pointer] = result.fLength;
    }
    return result;
}

CUTF16String content(PA_Unistring value) {
    if (!value.fString) {
        require(value.fLength == 0, "null nonempty string");
        return {};
    }
    PA_Unichar* pointer = value.fString;
    auto it = strings.find(pointer);
    require(it != strings.end() && it->second == value.fLength,
            "borrowed string read after disposal or wrong length");
    require(value.fString[value.fLength] == 0, "missing UTF-16 terminator");
    return CUTF16String(value.fString, value.fLength);
}

void disposeString(PA_Unistring value) {
    if (value.fString) {
        PA_Unichar* pointer = value.fString;
        require(strings.erase(pointer) == 1, "double string disposal");
        std::free(value.fString);
    }
}

struct Node {
    size_t refs = 1;
    std::map<CUTF16String, PA_Variable> properties;
};
std::set<Node*> nodes;

Node* newNode() {
    Node* node = new Node;
    nodes.insert(node);
    return node;
}

void clear(PA_Variable& value);

void release(Node* node) {
    if (!node) return;
    require(nodes.count(node), "reference read after disposal");
    if (--node->refs == 0) {
        for (auto& pair : node->properties) clear(pair.second);
        nodes.erase(node);
        delete node;
    }
}

PA_Variable copy(PA_Variable value) {
    if (value.fType == eVK_Unistring) {
        CUTF16String text = content(value.uValue.fString);
        value.uValue.fString = makeString(text.c_str());
    } else if (value.fType == eVK_Object || value.fType == eVK_Collection) {
        Node* node = static_cast<Node*>(value.uValue.fObject);
        if (node) {
            require(nodes.count(node), "copy of disposed reference");
            ++node->refs;
        }
    } else if (value.fType == eVK_Picture && value.uValue.fPicture) {
        PA_Picture picture = value.uValue.fPicture;
        require(pictures.count(picture), "copy of disposed picture");
        value.uValue.fPicture = std::malloc(1);
        picture = value.uValue.fPicture;
        pictures.insert(picture);
    }
    return value;
}

void clear(PA_Variable& value) {
    switch (value.fType) {
        case eVK_Unistring: disposeString(value.uValue.fString); break;
        case eVK_Object:
        case eVK_Collection: release(static_cast<Node*>(value.uValue.fObject)); break;
        case eVK_Picture:
            if (value.uValue.fPicture) {
                PA_Picture picture = value.uValue.fPicture;
                require(pictures.erase(picture) == 1, "double picture disposal");
                std::free(value.uValue.fPicture);
            }
            break;
        case eVK_ArrayUnicode: {
            auto& array = value.uValue.fArray;
            auto elements = reinterpret_cast<PA_Unistring*>(*array.fData);
            for (int i = 0; i <= array.fNbElements; ++i) disposeString(elements[i]);
            PA_DisposeHandle(array.fData);
            break;
        }
        default: break;
    }
    value = {};
    value.fType = eVK_Undefined;
}

PA_Variable callbackResult() {
    ++callbackCount;
    PA_Variable value = {};
    value.fType = callbackKind;
    if (callbackKind == eVK_Unistring) value.uValue.fString = makeString(sample.c_str());
    if (callbackKind == eVK_Object || callbackKind == eVK_Collection)
        value.uValue.fObject = newNode();
    if (callbackKind == eVK_Boolean) value.uValue.fBoolean = abortCallback;
    return value;
}

void engine(short selector, EngineBlock* eb) {
    eb->fError = eER_NoErr;
    switch (selector) {
        case EX_CREATE_UNISTRING:
            eb->fUniString1 = makeString(reinterpret_cast<PA_Unichar*>(eb->fHandle));
            break;
        case EX_DISPOSE_UNISTRING: disposeString(eb->fUniString1); break;
        case EX_SET_UNISTRING: {
            // Copy before disposing: input may alias the old content.
            CUTF16String text(reinterpret_cast<PA_Unichar*>(eb->fHandle));
            disposeString(eb->fUniString1);
            eb->fUniString1 = makeString(text.c_str());
            break;
        }
        case EX_VARIABLE_TO_STRING: {
            auto value = reinterpret_cast<PA_Variable*>(eb->fHandle);
            require(value->fType == eVK_Unistring, "unexpected string coercion");
            content(value->uValue.fString);
            eb->fUniString1 = value->uValue.fString;
            break;
        }
        case EX_CLEAR_VARIABLE: clear(*static_cast<PA_Variable*>(eb->fPtr1)); break;
        case EX_HANDLE_MANAGER: {
            PA_Handle h = eb->fHandle;
            switch (eb->fParam1) {
                case 1:
                    h = static_cast<PA_Handle>(std::malloc(sizeof(char*)));
                    *h = static_cast<char*>(std::calloc(1, eb->fParam2));
                    handles[h] = eb->fParam2;
                    eb->fHandle = h;
                    break;
                case 2:
                    require(handles.erase(h) == 1, "double handle disposal");
                    std::free(*h);
                    std::free(h);
                    break;
                case 3:
                    require(handles.count(h), "resize invalid handle");
                    *h = static_cast<char*>(std::realloc(*h, eb->fParam2));
                    handles[h] = eb->fParam2;
                    break;
                case 4: eb->fParam2 = handles.at(h); break;
                case 5: eb->fParam3 = reinterpret_cast<sLONG_PTR>(*h); break;
                case 6: case 7: case 8: break;
                default: require(false, "unknown handle operation");
            }
            break;
        }
        case EX_GET_METHOD_ID:
            eb->fParam1 = named || eb->fUName[0] == 0 ? 0 : 42;
            break;
        case EX_IS_PROCESS_DYING: eb->fManyToOne = dying; break;
        case EX_YIELD_ABSOLUTE: break;
        case EX_CALL_BY_PROCID: {
            require(eb->fParam1 == 42 && eb->fParam2 == 1, "method dispatch changed");
            auto values = reinterpret_cast<PA_Variable*>(*eb->fHandle);
            require(values[1].fType == eVK_Real, "callback argument changed");
            values[0] = callbackResult();
            break;
        }
        case EX_EXECUTE_COMMAND_BY_ID: {
            auto args = static_cast<PA_Variable**>(eb->fPtr1);
            auto result = static_cast<PA_Variable*>(eb->fPtr2);
            if (eb->fParam1 == 1007) {
                require(eb->fParam2 == 3, "named dispatch changed");
                require(content(args[0]->uValue.fString) == sample, "callback name changed");
                require(args[2]->fType == eVK_Real, "named real argument changed");
                ++callbackCount;
                args[1]->uValue.fBoolean = abortCallback;
                *result = {};
                result->fType = eVK_Undefined;
            } else if (eb->fParam1 == 1231) {
                Node* node = static_cast<Node*>(args[0]->uValue.fObject);
                *result = {};
                result->fType = eVK_Boolean;
                result->uValue.fBoolean = node->properties.count(content(args[1]->uValue.fString));
            } else {
                require(false, "unexpected command");
            }
            break;
        }
        case EX_SET_OBJ_VALUE: {
            Node* node = static_cast<Node*>(eb->fPtr1);
            CUTF16String key = content(eb->fUniString1);
            auto it = node->properties.find(key);
            if (it != node->properties.end()) clear(it->second);
            node->properties[key] = copy(*static_cast<PA_Variable*>(eb->fPtr2));
            break;
        }
        case EX_GET_OBJ_VALUE: {
            Node* node = static_cast<Node*>(eb->fPtr1);
            *static_cast<PA_Variable*>(eb->fPtr2) = copy(node->properties.at(content(eb->fUniString1)));
            break;
        }
        case EX_CREATE_PICTURE: {
            PA_Picture picture = std::malloc(1);
            eb->fPicture = picture;
            pictures.insert(picture);
            break;
        }
        default:
            fprintf(stderr, "unexpected engine selector: %d\n", selector);
            std::exit(1);
    }
}

void balanced() {
    require(strings.empty(), "unreleased string owner");
    require(nodes.empty(), "unreleased object/collection owner");
    require(handles.empty(), "unreleased handle owner");
    require(pictures.empty(), "unreleased picture owner");
}

void scan(const char* path, bool withCallback) {
    NSURL* url = [NSURL fileURLWithPath:[NSString stringWithUTF8String:path] isDirectory:YES];
    CFStringRef hfs = CFURLCopyFileSystemPath((CFURLRef)url, kCFURLHFSPathStyle);
    CUTF16String folder(CFStringGetLength(hfs), 0);
    CFStringGetCharacters(hfs, CFRangeMake(0, folder.size()), folder.data());
    CFRelease(hfs);
    PA_Unistring input = makeString(folder.c_str());
    PA_Unistring method = makeString(withCallback ? sample.c_str() : CUTF16String().c_str());
    void* args[] = { &input, &method };
    double total = -1;
    double* result = &total;
    PluginBlock params = {};
    params.fParameters = args;
    params.fResult = &result;
    callbackCount = 0;
    PluginMain(1, &params);
    double expected = (dying || (withCallback && abortCallback)) ? 0 : 16384;
    if (total != expected)
        fprintf(stderr, "total=%g expected=%g callbacks=%d\n", total, expected, callbackCount);
    require(total == expected,
            "folder total or abort semantics changed");
    require(callbackCount == (withCallback && !dying ? (abortCallback ? 1 : 2) : 0),
            "callback cadence changed");
    disposeString(input);
    disposeString(method);
    balanced();
}

void setters() {
    Node* node = newNode();
    const CUTF16String ascii = {'A', 'S', 'C', 'I', 'I'};
    for (const CUTF16String& text : {sample, ascii, CUTF16String()}) {
        const char* utf8 = text.empty() ? "" : (text == ascii ? "ASCII" :
            reinterpret_cast<const char*>(sample8.c_str()));
        const wchar_t* wide = text.empty() ? L"" : (text == ascii ? L"ASCII" :
            L"A\u65e5\U0001f680");
        for (int i = 0; i < 4; ++i) {
            if (i == 0) ob_set_s(node, "key", utf8);
            if (i == 1) ob_set_s(node, L"key", utf8);
            if (i == 2) ob_set_a(node, L"key", wide);
            if (i == 3) ob_set_a(node, L"key", &text);
            require(content(node->properties.at(CUTF16String({'k','e','y'})).uValue.fString) == text,
                    "JSON setter Unicode content changed");
        }
    }
    PA_Picture picture = PA_CreatePicture(nullptr, 0);
    ob_set_p(node, L"picture", picture); // Existing helper consumes its input.
    release(node);
    balanced();
}

void getters() {
    Node* node = newNode();
    const CUTF16String key = {'k','e','y'};
    for (int kind : {eVK_Unistring, eVK_Object, eVK_Collection, eVK_Boolean, eVK_Real}) {
        PA_Variable value = {};
        value.fType = kind;
        if (kind == eVK_Unistring) value.uValue.fString = makeString(sample.c_str());
        if (kind == eVK_Object || kind == eVK_Collection) value.uValue.fObject = newNode();
        if (kind == eVK_Boolean) value.uValue.fBoolean = true;
        if (kind == eVK_Real) value.uValue.fReal = 123;
        node->properties[key] = value;
        for (int repeat = 0; repeat < 3; ++repeat) {
            CUTF8String text;
            require(ob_get_a(node, L"key", &text), "existing property lost");
            require(text == (kind == eVK_Unistring ? sample8 : CUTF8String()),
                    "getter content changed");
            require(ob_get_b(node, L"key") == (kind == eVK_Boolean), "Boolean getter changed");
            require(ob_get_n(node, L"key") == (kind == eVK_Real ? 123 : 0), "real getter changed");
            PA_CollectionRef collection = ob_get_c(node, L"key");
            require((collection != nullptr) == (kind == eVK_Collection), "collection handoff changed");
            if (collection) PA_DisposeCollection(collection);
        }
        clear(node->properties[key]);
        node->properties.erase(key);
    }
    CUTF8String absent;
    require(!ob_get_a(node, L"missing", &absent), "missing property changed");
    PA_Variable empty = {};
    PA_Unichar terminator = 0;
    PA_Unistring emptyString = makeString(&terminator);
    PA_SetStringVariable(&empty, &emptyString);
    node->properties[key] = empty;
    CUTF8String emptyOutput = sample8;
    require(ob_get_a(node, L"key", &emptyOutput) && emptyOutput.empty(),
            "empty getter content changed");
    release(node);
    balanced();
}

void contracts() {
    PA_Variable scalar = PA_CreateVariable(eVK_Unistring);
    PA_SetUnistring(&scalar.uValue.fString, const_cast<PA_Unichar*>(sample.c_str()));
    require(content(PA_GetStringVariable(scalar)) == sample, "scalar setter copy changed");
    PA_ClearVariable(&scalar);
    ARRAY_TEXT wrapper;
    wrapper.appendUTF16String(sample.c_str());
    wrapper.appendUTF16String(CUTF16String().c_str());
    PA_Variable array = PA_CreateVariable(eVK_ArrayUnicode);
    BytePtr args[] = { reinterpret_cast<BytePtr>(&array) };
    for (int i = 0; i < 3; ++i) {
        wrapper.toParamAtIndex(args, 1);
        require(content(PA_GetStringInArray(array, 0)) == sample, "index zero transfer changed");
        require(content(PA_GetStringInArray(array, 1)).empty(), "empty element changed");
        ARRAY_TEXT read;
        read.fromParamAtIndex(args, 1);
        CUTF16String text;
        read.copyUTF16StringAtIndex(&text, 0);
        require(text == sample, "borrowed array copy changed");
    }
    PA_ResizeArray(&array, 0);
    PA_ClearVariable(&array);
    PA_Unistring rejected = makeString(sample.c_str());
    PA_Variable wrongType = PA_CreateVariable(eVK_Real);
    PA_SetStringInArray(wrongType, 0, &rejected);
    require(content(rejected) == sample, "wrong-type transfer consumed input");
    PA_Variable nullArray = {};
    nullArray.fType = eVK_ArrayUnicode;
    PA_SetStringInArray(nullArray, 0, &rejected);
    require(content(rejected) == sample, "null-data transfer consumed input");
    PA_DisposeUnistring(&rejected);
    PA_ClearVariable(&wrongType);
    for (int index : {-1, 1}) {
        PA_Variable empty = PA_CreateVariable(eVK_ArrayUnicode);
        PA_Unistring rejected = makeString(sample.c_str());
        PA_SetStringInArray(empty, index, &rejected);
        require(content(rejected) == sample, "rejected transfer consumed input");
        PA_DisposeUnistring(&rejected);
        PA_ClearVariable(&empty);
    }
    balanced();
}
}

int main(int argc, char** argv) {
    require(argc == 4, "expected case, empty model, tree path");
    allocatedEmpty = std::strcmp(argv[2], "allocated") == 0;
    gCall4D = engine;
    @autoreleasepool {
        std::string mode(argv[1]);
        if (mode == "named") {
            named = true;
            for (bool abort : {false, true}) {
                abortCallback = abort;
                scan(argv[3], true);
            }
        } else if (mode == "callbacks") {
            for (int kind : {eVK_Unistring, eVK_Object, eVK_Collection, eVK_Undefined, eVK_Boolean}) {
                callbackKind = kind;
                abortCallback = false;
                scan(argv[3], true);
            }
            abortCallback = true;
            scan(argv[3], true);
            dying = true;
            scan(argv[3], true);
            dying = false;
            abortCallback = false;
            scan(argv[3], false);
        } else if (mode == "setters") setters();
        else if (mode == "getters") getters();
        else if (mode == "contracts") contracts();
        else require(false, "unknown case");
    }
    balanced();
    puts("ownership, Unicode and cleanup checks passed");
}
